# hugo-sqlite-proto — Práctica SGBD P1.1 (2º ASIR)

Prototipo didáctico: **Hugo** genera HTML estático desde Markdown y **SQLite** trabaja
**solo en tiempo de build** (indexar y agregar). En producción: ficheros estáticos, nada más.

* **Alumno:** Sergio Batres López
* **Módulo:** Sistemas Gestores de Bases de Datos (2º ASIR)
* **Repositorio Fork:** [https://github.com/Jldomingo17/hugo-sqlite-proto](https://github.com/Jldomingo17/hugo-sqlite-proto)
* **Demo en vivo (GitHub Pages):** [https://jldomingo17.github.io/hugo-sqlite-proto/](https://jldomingo17.github.io/hugo-sqlite-proto/)
* **Profesor Colaborador invitado:** `fenix011`

---

## Flujo del Prototipo (Filosofía Unix)

```
content/*.md --> tools/index.py --> build/site.db --+--> static/search.json --> navegador (search.js)
 (Markdown)       (parsea + INSERT)   (SQLite, local) +--> data/tags.json -----> Hugo (layouts/index.html)
                                                     +--> data/stats.json ----> Hugo (layouts/partials/footer.html)

                                     hugo --> public/   <- lo único que se despliega
```

`build/`, `static/search.json`, `data/tags.json` y `data/stats.json` están en `.gitignore`: se **regeneran** en cada build.

---

## Solución Detallada de los Ejercicios

### Ejercicio 1: Añadir post con `tags: [sql]` y comprobar conteo de etiquetas
* **Acción:** Se creó el post `content/posts/consultas-sql-en-sqlite.md` con las etiquetas `tags: [sql, sqlite, bases-de-datos]`.
* **Resultado:** Al ejecutar `make index` (o `make serve`), el script `tools/index.py` lee el nuevo archivo, inserta los registros en la tabla `tags` de SQLite y la consulta `Q_TAGS` agrupa por `tag` calculando el nuevo `total` de cada etiqueta. La etiqueta `sql` aparece ahora en la portada (`layouts/index.html`) con su conteo actualizado.

### Ejercicio 2: Añadir flag `--drafts` a `tools/index.py`
* **¿Por qué `hugo server -D` mostraba borradores pero la búsqueda no?**:
  `hugo server -D` lee directamente los archivos Markdown con `draft: true`. Sin embargo, `tools/index.py` descartaba explícitamente estos archivos mediante `if not page["draft"]`, impidiendo que se indexaran en la base de datos `build/site.db` y por ende omitiéndolos de `static/search.json`.
* **Solución aplicada:** Se añadió el parámetro `include_drafts` a `read_all()` y se comprobó la presencia de los argumentos `--drafts` o `-D` en la línea de comandos (`sys.argv`). Además, se actualizó la regla `serve` del `Makefile` para ejecutar `python3 tools/index.py --drafts && hugo server -D`, garantizando que en modo desarrollo los borradores (como `borrador.md`) también sean indexados y encontrados por el buscador.

### Ejercicio 3: Tabla `words(url, n)` y visualización de palabras totales en el pie
* **Esquema relacional:** Se añadió la tabla `words` al esquema SQLite:
  ```sql
  CREATE TABLE words (
    url TEXT PRIMARY KEY REFERENCES posts(url),
    n   INTEGER NOT NULL
  );
  ```
* **Extracción y agregación:** Se implementó la función pura `count_words(text)` para contabilizar las palabras de cada artículo y se creó la consulta de agregación `Q_STATS`:
  ```sql
  SELECT json_object(
    'total_words', COALESCE(SUM(n), 0),
    'avg_words', COALESCE(ROUND(AVG(n), 1), 0),
    'total_posts', COUNT(*)
  )
  FROM words;
  ```
* **Visualización:** El resultado se exporta a `data/stats.json` y se muestra dinámicamente en `layouts/partials/footer.html`, visualizando el total de palabras indexadas, el número de artículos y la media de palabras por post.

### Ejercicio 4: Ordenación de resultados de búsqueda por relevancia en `static/search.js`
* **Función pura de scoring:** En `static/search.js` se implementó la función pura `score(terms)(post)`, la cual calcula el número de apariciones de los términos de búsqueda en el texto, otorgando una ponderación adicional (+3) a las coincidencias encontradas en el título del artículo.
* **Ordenación:** El array de resultados se ordena de mayor a menor relevancia (`.sort((a, b) => b.relevance - a.relevance)`) antes de inyectarlo en el DOM, manteniendo la pureza funcional del módulo.

### Ejercicio 5: Despliegue en GitHub Pages y análisis de procesos en el servidor
* **Despliegue:** El sitio estático compilado en `public/` fue desplegado en la rama `gh-pages` y publicado mediante GitHub Pages en:  
  [https://jldomingo17.github.io/hugo-sqlite-proto/](https://jldomingo17.github.io/hugo-sqlite-proto/)
* **¿Qué proceso corre en el servidor?:**  
  **Ninguno de los nuestros.** En el servidor web no se ejecuta ningún intérprete de Python, ningún daemon de base de datos ni ningún proceso de SQLite en segundo plano. El servidor web es un mero despachador HTTP de archivos estáticos planos (`.html`, `.css`, `.js`, `.json`). Todo el cómputo de la base de datos se resolvió previamente en la máquina local durante el tiempo de construcción (*build-time*).

---

## Comandos del Makefile

```bash
make            # Muestra la ayuda
make serve      # Indexa (incluyendo borradores) y arranca servidor local en http://localhost:1313/
make build      # Indexa y compila el sitio estático optimizado en public/
make check      # Valida que search.json, tags.json y stats.json son JSON válidos
make clean      # Limpia archivos generados temporales
```
