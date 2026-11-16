#!/usr/bin/env python3
"""tools/migrar.py — content/posts/*.md → base de datos SQLite de Chyrp Lite.

Filosofía Unix, como tools/index.py: hace UNA cosa. Lee los Markdown de tu
blog (P1.1), los convierte a las filas que espera Chyrp Lite y las inserta.

  extraer     (disco)  → lista de dicts con lo que dice cada .md
  transformar (PURA)   → dict con la fila de `posts` y sus atributos
  cargar      (SQL)    → INSERT dentro de UNA transacción, sin duplicar

Chyrp Lite guarda cada entrada en dos tablas:
  posts(id, feather, clean, url, pinned, status, user_id, created_at, updated_at)
  post_attributes(post_id, name, value)   ← título, cuerpo y etiquetas (EAV)

Ejercicios resueltos:
  - Ejercicio 1: Simulación de fallo de transacción (--romper-transaccion)
  - Ejercicio 2: Migración de páginas sueltas a la tabla pages (--paginas)
  - Ejercicio 5: Soporte de etiquetas numéricas como 2026
"""
import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# Asegurar import de index.py esté donde esté ejecutado
sys.path.insert(0, str(Path(__file__).resolve().parent))
from index import parse_meta, split_front_matter

# Valor que usa Chyrp Lite para "esta entrada nunca se ha editado".
SQL_DATETIME_ZERO = "1000-01-01 00:00:00"

# --- funciones puras ---------------------------------------------------------

def slugify(texto):
    """'Árbol B' → 'arbol-b' (algo parecido al campo `clean` de Chyrp Lite)."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")
    return slug or "item"


def fecha_chyrp(valor, por_defecto):
    """'2026-10-27' o '2026-10-27T09:30' → '2026-10-27 09:30:00'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::(\d{2}))?)?", str(valor))
    if not m:
        return por_defecto
    dia, hora_min, seg = m.groups()
    return f"{dia} {hora_min or '00:00'}:{seg or '00'}"


def etiquetas_json(nombres):
    """['sql', 'Árbol B', 2026] → '{"sql":"sql","\\u00c1rbol B":"arbol-b","2026":"2026"}'.

    Es el formato exacto con el que el módulo Tags guarda las etiquetas en
    post_attributes: un objeto JSON {nombre: slug}. Sin etiquetas guarda '[]'.
    """
    if not nombres:
        return "[]"
    asociacion = {str(nombre): slugify(nombre) for nombre in nombres}
    # PHP escribe "/" como "\/" y Python no: igualamos los bytes.
    return json.dumps(asociacion, separators=(",", ":")).replace("/", "\\/")


def leer_entrada(path):
    """Un .md → dict con lo que nos interesa. Pura salvo por leer el fichero."""
    front, cuerpo = split_front_matter(path.read_text(encoding="utf-8"))
    meta = parse_meta(front)
    tags = meta.get("tags", [])
    return {
        "slug": path.stem,
        "titulo": meta.get("title", path.stem),
        "fecha": str(meta.get("date", "")),
        "cuerpo": cuerpo.strip(),
        "tags": tags if isinstance(tags, list) else [tags],
        "draft": meta.get("draft", False) is True,
    }


def leer_pagina(path):
    """content/*.md (ej. about.md) → dict para la tabla `pages`."""
    front, cuerpo = split_front_matter(path.read_text(encoding="utf-8"))
    meta = parse_meta(front)
    return {
        "slug": path.stem,
        "titulo": meta.get("title", path.stem.capitalize()),
        "cuerpo": cuerpo.strip(),
        "public": 0 if meta.get("draft", False) else 1,
    }


def transformar(entrada, user_id, ahora):
    """Entrada del prototipo → filas para Chyrp Lite. Sin disco ni SQL."""
    slug = slugify(entrada["slug"])
    return {
        "post": {
            "feather": "text",
            "clean": slug,
            "url": slug,
            "pinned": 0,
            "status": "draft" if entrada["draft"] else "public",
            "user_id": user_id,
            "created_at": fecha_chyrp(entrada["fecha"], ahora),
            "updated_at": SQL_DATETIME_ZERO,
        },
        "attrs": {
            "title": entrada["titulo"],
            "body": entrada["cuerpo"],
            "tags": etiquetas_json(entrada["tags"]),
        },
    }


def transformar_pagina(pagina, user_id, ahora):
    """(Ejercicio 2) Página suelta → fila para tabla `pages`."""
    slug = slugify(pagina["slug"])
    return {
        "title": pagina["titulo"],
        "body": pagina["cuerpo"],
        "public": pagina.get("public", 1),
        "show_in_list": 1,
        "list_order": 0,
        "clean": slug,
        "url": slug,
        "user_id": user_id,
        "parent_id": 0,
        "created_at": ahora,
        "updated_at": SQL_DATETIME_ZERO,
    }

# --- efectos: disco y SQL ----------------------------------------------------

def extraer(origen):
    ficheros = (p for p in sorted(Path(origen).rglob("*.md")) if p.name != "_index.md")
    return [leer_entrada(p) for p in ficheros]


def extraer_paginas(origen):
    """(Ejercicio 2) Extrae ficheros .md fuera de posts (ej: content/about.md)."""
    p = Path(origen)
    if not p.is_dir():
        return []
    ficheros = [f for f in p.glob("*.md") if f.name != "_index.md"]
    return [leer_pagina(f) for f in ficheros]


def comprobar_destino(destino):
    """Falla con un mensaje claro si no es una base de datos de Chyrp Lite."""
    if not Path(destino).is_file():
        sys.exit(f"migrar.py: no existe {destino} (instala Chyrp Lite antes)")
    con = sqlite3.connect(destino)
    tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    if not {"posts", "post_attributes", "users"} <= tablas:
        sys.exit(f"migrar.py: {destino} no parece una base de datos de Chyrp Lite")


def buscar_autor(con, login):
    sql, params = (("SELECT id FROM users WHERE login = ?", (login,)) if login
                   else ("SELECT MIN(id) FROM users", ()))
    fila = con.execute(sql, params).fetchone()
    if fila is None or fila[0] is None:
        sys.exit("migrar.py: no encuentro ese autor en la tabla users")
    return fila[0]


def existe(con, url):
    return con.execute("SELECT 1 FROM posts WHERE url = ?", (url,)).fetchone() is not None


def existe_pagina(con, url):
    return con.execute("SELECT 1 FROM pages WHERE url = ?", (url,)).fetchone() is not None


def insertar(con, fila, contador_nuevas=0, romper_en=0):
    """Inserta en posts y post_attributes. Permite simular fallo en transacción."""
    if romper_en and contador_nuevas == romper_en:
        raise RuntimeError(f"Fallo forzado intencionado en la entrada nueva #{contador_nuevas} (Ejercicio 1)")

    columnas = list(fila["post"])
    cur = con.execute(
        f"INSERT INTO posts({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
        [fila["post"][c] for c in columnas])
    con.executemany(
        "INSERT INTO post_attributes(post_id, name, value) VALUES (?, ?, ?)",
        [(cur.lastrowid, nombre, valor) for nombre, valor in fila["attrs"].items()])
    return cur.lastrowid


def insertar_pagina(con, fila):
    columnas = list(fila)
    cur = con.execute(
        f"INSERT INTO pages({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
        [fila[c] for c in columnas])
    return cur.lastrowid


def cargar(destino, filas, simulacro=False, romper_en=0, usar_transaccion=True):
    """Inserta lo que falte. Devuelve [(estado, url)]. Una sola transacción."""
    con = sqlite3.connect(destino)
    try:
        if usar_transaccion:
            with con:  # commit si todo va bien, rollback si algo falla
                return _ejecutar_inserciones(con, filas, simulacro, romper_en)
        else:
            # Sin bloque transaccional 'with con': autocommit parcial para Ejercicio 1
            con.isolation_level = None
            return _ejecutar_inserciones(con, filas, simulacro, romper_en)
    finally:
        con.close()


def _ejecutar_inserciones(con, filas, simulacro, romper_en):
    resultado = []
    contador = 0
    for fila in filas:
        url = fila["post"]["url"]
        if existe(con, url):
            resultado.append(("omitida", url))
            continue
        contador += 1
        if not simulacro:
            insertar(con, fila, contador_nuevas=contador, romper_en=romper_en)
        resultado.append(("simulada" if simulacro else "creada", url))
    return resultado


def cargar_paginas(destino, filas_paginas, simulacro=False):
    """(Ejercicio 2) Inserta páginas en la tabla `pages` dentro de una transacción."""
    con = sqlite3.connect(destino)
    try:
        with con:
            resultado = []
            for fila in filas_paginas:
                url = fila["url"]
                if existe_pagina(con, url):
                    resultado.append(("omitida", url))
                    continue
                if not simulacro:
                    insertar_pagina(con, fila)
                resultado.append(("creada", url))
            return resultado
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description="Markdown (P1.1) → SQLite de Chyrp Lite")
    ap.add_argument("--origen", default="content/posts", help="carpeta con los .md de posts")
    ap.add_argument("--destino", required=True, help="fichero .sqlite de Chyrp Lite (¡una COPIA!)")
    ap.add_argument("--autor", help="login del autor en Chyrp Lite (por defecto, el primer usuario)")
    ap.add_argument("--simulacro", action="store_true", help="muestra qué haría, sin escribir")
    ap.add_argument("--romper-transaccion", type=int, default=0, help="Ejercicio 1: fuerza fallo en la N-ésima entrada nueva")
    ap.add_argument("--sin-transaccion", action="store_true", help="Ejercicio 1: deshabilita rollback para comparar")
    ap.add_argument("--paginas", default="content", help="Ejercicio 2: migra páginas desde esta carpeta")
    args = ap.parse_args()

    comprobar_destino(args.destino)
    entradas = extraer(args.origen)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    con = sqlite3.connect(args.destino)
    user_id = buscar_autor(con, args.autor)
    con.close()

    filas = [transformar(e, user_id, ahora) for e in entradas]
    resultado = cargar(args.destino, filas, args.simulacro,
                       romper_en=args.romper_transaccion,
                       usar_transaccion=not args.sin_transaccion)

    for estado, url in resultado:
        print(f"{estado:9} {url}")
    nuevas = sum(1 for estado, _ in resultado if estado not in ("omitida", "simulada"))
    if args.simulacro:
        nuevas = sum(1 for estado, _ in resultado if estado == "simulada")
    print(f"migrar: {len(entradas)} entradas leídas, {nuevas} nuevas, "
          f"{len(entradas) - nuevas} ya estaban")

    # Ejercicio 2: Migrar páginas si existen
    paginas = extraer_paginas(args.paginas)
    if paginas:
        filas_p = [transformar_pagina(p, user_id, ahora) for p in paginas]
        res_p = cargar_paginas(args.destino, filas_p, args.simulacro)
        print(f"\nmigrar paginas (Ejercicio 2): {len(res_p)} páginas procesadas.")
        for est, u in res_p:
            print(f"  {est:9} {u}")


if __name__ == "__main__":
    main()
