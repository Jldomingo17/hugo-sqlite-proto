---
title: "Consultas SQL y agregación de datos con SQLite en tiempo de build"
date: 2026-11-09
description: "Cómo SQLite permite transformar contenido estático y agregar etiquetas en tiempo de compilación para Hugo."
tags: [sql, sqlite, bases-de-datos]
---

El uso de **SQLite** en tiempo de compilación (*build-time*) representa lo mejor de dos mundos:
la flexibilidad de un motor relacional SQL y la velocidad imbatible de un sitio estático.

### ¿Por qué SQLite en tiempo de build?
En lugar de mantener un servidor de base de datos como MySQL o PostgreSQL corriendo en producción,
SQLite nos permite:

1. **Indexar contenido:** Leer los ficheros Markdown y almacenar sus campos estructurados en tablas relacionales (`posts`, `tags`, `words`).
2. **Generar JSON con SQL:** Mediante la extensión nativa `JSON1` de SQLite (`json_group_array`, `json_object`), las consultas SQL generan directamente las estructuras JSON que consume el buscador del navegador (`static/search.json`) y las plantillas de Hugo (`data/tags.json`, `data/stats.json`).
3. **Agregaciones instantáneas:** Consultas con `GROUP BY` y `COUNT(*)` calculan el número de artículos por etiqueta sin complejidad adicional.

### Ejemplo de consulta SQL de agregación

```sql
SELECT tag, COUNT(*) AS total
FROM tags
GROUP BY tag
ORDER BY total DESC, tag;
```

Al compilar, Hugo lee el fichero resultante y muestra las etiquetas con su conteo actualizado, sin requerir ninguna base de datos en el servidor web.
