# Herramienta de reconocimiento desarrollada

## Objetivo
Esta herramienta ha sido desarrollada como parte del Trabajo Fin de Grado realizado en la Universidad Internacional de La Rioja (UNIR).

El objetivo de la herramienta desarrollada es automatizar la etapa de reconocimiento establecida en la metodología sugerida. Su propósito fundamental es determinar la superficie de ataque de una API o una aplicación web a partir de una URL base, con el fin de disminuir la carga manual del analista en esta fase inicial.

La herramienta se fundamenta únicamente en métodos de análisis pasivo, que solo recopila datos disponibles al público sin efectuar pruebas intrusivas o aprovechar vulnerabilidades.

---

## Funcionamiento general

La herramienta opera siguiendo una serie de pasos secuenciales:

1. Se hace una solicitud inicial a la URL de destino.
2. Se examina el contenido HTML para obtener enlaces y recursos relacionados.
3. Se identifican ficheros JavaScript y se analizan en busca de posibles endpoints.
4. Se comprueba la existencia de documentación de API basada en estándares como OpenAPI o Swagger.
5. Se generan rutas adicionales a partir de patrones comunes en aplicaciones web.
6. Se realizan peticiones HTTP a cada endpoint identificado para obtener información relevante.
7. Se genera un informe estructurado con los resultados obtenidos.

---

## Técnicas de descubrimiento utilizadas

La herramienta combina diferentes técnicas para optimizar la cobertura del reconocimiento:

- Estudio de vínculos que aparecen en el código HTML.
- Utilización de expresiones regulares para extraer rutas a partir de archivos JavaScript.

- Verificación de rutas estándar donde generalmente se encuentra la documentación de las APIs.
- Creación de rutas comunes basadas en patrones regulares.
- Filtrado de los resultados para restringir el análisis al dominio pertinente.

Esta perspectiva posibilita una visión extensa de la superficie de ataque sin tener que implementar técnicas activas.

---

## Arquitectura del sistema

La herramienta fue creada utilizando una estructura modular y separando de manera clara las responsabilidades:

- **Módulo de comunicación:**  Emplea sesiones persistentes para llevar a cabo solicitudes HTTP.
- **Módulo de análisis HTML:** obtiene recursos y vínculos del contenido de la web.
- **Módulo de análisis de JavaScript:** encuentra posibles puntos finales usando patrones.
- **Módulo de descubrimiento:** fusiona las diferentes fuentes de información para crear nuevas rutas.
- **Módulo de análisis de respuestas:** compila datos tales como códigos HTTP, encabezados y tamaño de respuesta.
- **Módulo de generación de informes:** genera resultados en HTML y JSON.

Esta división permite que el sistema sea mantenido y ampliado con facilidad.

---

## Decisiones de diseño

Se han realizado varias decisiones importantes durante la creación de la herramienta:

- Empleo de Python por su facilidad de uso y la disponibilidad de bibliotecas para el análisis de páginas web.
- Aplicación de sesiones HTTP para optimizar la eficacia en las solicitudes.
- Uso de expresiones regulares para el análisis de JavaScript, sin necesidad de un parser completo.
- Restringir el análisis al dominio objetivo con el fin de prevenir un comportamiento no deseado.
---

## Resultados generados

La herramienta produce un informe organizado que contiene:

- Catálogo de endpoints hallados.
- Información de cada endpoint (código HTTP, tipo de contenido, tamaño).
- Encabezados de respuesta del servidor.
- Posible documentación de API identificada.

Este informe es la entrada para las etapas posteriores de la metodología.

---

## Limitaciones

Debido a su diseño, la herramienta tiene varias restricciones:

- No implementa ningún código JavaScript en el cliente, lo que podría restringir el análisis en aplicaciones contemporáneas.
- Al fundamentarse en patrones, el análisis de JavaScript no es capaz de detectar todos los casos posibles.
- No lleva a cabo la autenticación, solo examina los recursos que son accesibles al público.
- No lleva a cabo ensayos ni explotación de vulnerabilidades.

Estas limitaciones son coherentes con la finalidad de la herramienta, que está enfocada únicamente en la etapa de reconocimiento.

---

## Consideraciones éticas

La herramienta ha sido creada para ser utilizada en contextos autorizados y controlados, utilizando solamente estrategias pasivas. Su uso en sistemas sin autorización puede constituir una violación de la legislación actual.


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
