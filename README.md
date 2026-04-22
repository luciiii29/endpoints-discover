# Herramienta de reconocimiento desarrollada

## Objetivo

La herramienta desarrollada tiene como finalidad automatizar la fase de reconocimiento definida en la metodología propuesta. Su objetivo principal es identificar la superficie de ataque de una aplicación web o API a partir de una URL base, reduciendo el esfuerzo manual del analista en esta etapa inicial.

La herramienta se basa exclusivamente en técnicas de análisis pasivo, limitándose a recopilar información accesible públicamente sin realizar pruebas intrusivas ni explotación de vulnerabilidades.

---

## Funcionamiento general

El funcionamiento de la herramienta se basa en una serie de pasos secuenciales:

1. Se realiza una petición inicial a la URL objetivo.
2. Se analiza el contenido HTML para extraer enlaces y recursos asociados.
3. Se identifican ficheros JavaScript y se analizan en busca de posibles endpoints.
4. Se comprueba la existencia de documentación de API basada en estándares como OpenAPI o Swagger.
5. Se generan rutas adicionales a partir de patrones comunes en aplicaciones web.
6. Se realizan peticiones HTTP a cada endpoint identificado para obtener información relevante.
7. Se genera un informe estructurado con los resultados obtenidos.

---

## Técnicas de descubrimiento utilizadas

Para maximizar la cobertura del reconocimiento, la herramienta combina distintas técnicas:

- Análisis de enlaces presentes en el código HTML.
- Extracción de rutas a partir de ficheros JavaScript mediante expresiones regulares.
- Consulta de rutas estándar donde suele encontrarse documentación de APIs.
- Generación de rutas comunes basadas en patrones habituales.
- Filtrado de resultados para limitar el análisis al dominio objetivo.

Este enfoque permite obtener una visión amplia de la superficie de ataque sin necesidad de realizar técnicas activas.

---

## Arquitectura del sistema

La herramienta ha sido desarrollada siguiendo una arquitectura modular, diferenciando claramente las responsabilidades:

- **Módulo de comunicación:** realiza peticiones HTTP utilizando sesiones persistentes.
- **Módulo de análisis HTML:** extrae enlaces y recursos del contenido web.
- **Módulo de análisis de JavaScript:** identifica posibles endpoints mediante patrones.
- **Módulo de descubrimiento:** combina las distintas fuentes de información para generar nuevas rutas.
- **Módulo de análisis de respuestas:** recoge información como códigos HTTP, cabeceras y tamaño de respuesta.
- **Módulo de generación de informes:** produce salidas en formato JSON y HTML.

Esta separación facilita la extensibilidad y el mantenimiento del sistema.

---

## Decisiones de diseño

Durante el desarrollo de la herramienta se han tomado varias decisiones relevantes:

- Uso de Python por su simplicidad y disponibilidad de librerías para análisis web.
- Utilización de sesiones HTTP para mejorar la eficiencia en las peticiones.
- Aplicación de expresiones regulares para el análisis de JavaScript, evitando la complejidad de un parser completo.
- Limitación del análisis al dominio objetivo para evitar comportamiento no deseado.

Estas decisiones permiten mantener un equilibrio entre funcionalidad y simplicidad.

---

## Resultados generados

La herramienta genera un informe estructurado que incluye:

- Lista de endpoints descubiertos.
- Información de cada endpoint (código HTTP, tipo de contenido, tamaño).
- Cabeceras de respuesta del servidor.
- Posible documentación de API detectada.

Este informe constituye la entrada para las fases posteriores de la metodología.

---

## Limitaciones

La herramienta presenta varias limitaciones derivadas de su diseño:

- No ejecuta código JavaScript en el cliente, lo que puede limitar el análisis en aplicaciones modernas.
- El análisis de JavaScript se basa en patrones, por lo que no detecta todos los casos posibles.
- No gestiona autenticación, analizando únicamente recursos accesibles públicamente.
- No realiza pruebas de vulnerabilidad ni explotación.

Estas limitaciones son coherentes con el objetivo de la herramienta, centrado exclusivamente en la fase de reconocimiento.

---

## Consideraciones éticas

La herramienta ha sido diseñada para su uso en entornos controlados y autorizados, aplicando únicamente técnicas pasivas. Su utilización en sistemas sin consentimiento puede suponer una vulneración de la normativa vigente.

---

## Instalación y uso

### Requisitos

- Python 3.10 o superior.
- Dependencias recogidas en `requirements.txt`.

### Instalación

```bash
pip install -r requirements.txt
```

### Ejecución básica

```bash
python recon.py https://ejemplo.com
```

### Ejecución con parámetros personalizados

```bash
python recon.py https://ejemplo.com --output informe --format both --depth 2 --max-urls 300 --delay 0.3
```

### Parámetros disponibles

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `url` | *(obligatorio)* | URL base del objetivo (debe empezar por `http://` o `https://`). |
| `-o`, `--output` | `recon_report` | Prefijo de los archivos de salida. |
| `--format` | `both` | Formato del informe: `json`, `html` o `both`. |
| `--depth` | `1` | Profundidad del crawler (0 = solo la raíz). |
| `--max-urls` | `200` | Número máximo de URLs a visitar. |
| `--delay` | `0.2` | Segundos de espera entre peticiones. |
| `--max-js` | `10` | Número máximo de ficheros JS a analizar. |

---

## Estructura del proyecto

```
herramienta python/
├── recon.py           # Código principal de la herramienta
├── requirements.txt   # Dependencias del proyecto
└── README.md          # Documentación del proyecto
```
