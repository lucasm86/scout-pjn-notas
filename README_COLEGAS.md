# Scout PJN — Dejar notas · Guía para colegas

App de escritorio para **Windows** que deja nota automáticamente en **todos tus
expedientes** del portal SCW del PJN, los **martes y viernes**, a la hora que
elijas. No necesitás instalar Python ni nada: es un solo archivo `.exe`.

> **Aviso:** software libre de uso personal, **sin garantía**, se usa **bajo tu
> propia responsabilidad**. No tiene relación ni aval del Poder Judicial. Solo
> automatiza, con **tus** credenciales, algo que podés hacer a mano. Detalle en
> el repositorio: https://github.com/lucasm86/scout-pjn-notas

---

## 1. Instalación

1. Copiá `ScoutPJN-DejarNotas.exe` donde quieras (por ejemplo, el Escritorio).
2. La primera vez, Windows puede mostrar un cartel azul de **SmartScreen**
   ("Windows protegió tu PC") porque el `.exe` no está firmado. Es esperable:
   hacé clic en **"Más información" → "Ejecutar de todas formas"**.
3. Si tu antivirus lo marca, es un **falso positivo** típico de este tipo de
   empaquetado; permitilo o agregá una excepción.

## 2. Configuración (primera vez)

Hacé **doble clic** en el `.exe`. Se abre la ventana de configuración:

1. Escribí tu **usuario (CUIL)** y tu **contraseña** del PJN.
2. Clic en **"Probar login"**. Se abre un navegador y valida tu ingreso:
   - Si dice **✅ conexión OK**, listo (tu sesión queda guardada).
   - Si aparece un **captcha** o un segundo factor, **resolvelo en esa ventana**;
     queda guardado para las corridas automáticas.
   - Si dice ❌, revisá usuario/contraseña.
3. Elegí la **hora** (formato `HH:MM`, 24 h) a la que querés que corra los
   martes y viernes.
4. Clic en **"Guardar y agendar"**. Eso guarda tu contraseña de forma segura y
   programa la tarea automática.

Con eso ya está: **no tenés que abrir la app de nuevo**. Va a correr sola.

## 3. ¿Cómo sé que funcionó?

- Cada corrida escribe un **registro** en:
  `%LOCALAPPDATA%\scout-pjn-notas\registros\notas_AAAA-MM-DD_HHMMSS.txt`
  (pegá esa ruta en el explorador de archivos). Ahí ves cuántas notas dejó,
  cuántas ya tenían y si hubo algún problema.
- El detalle técnico de la última corrida queda en
  `%LOCALAPPDATA%\scout-pjn-notas\app.log`.

## 4. Botones de la ventana

- **Probar login** — valida tu ingreso y guarda la sesión.
- **Guardar y agendar** — guarda credenciales + programa martes y viernes.
- **Simulacro (no deja notas)** — hace todo el recorrido (login, navegación) pero
  **no deja ninguna nota**. Ideal para probar sin efectos.
- **Correr ahora** — deja las notas ya mismo (a demanda). Recordá: el portal solo
  permite nota los **martes y viernes**.
- **Acerca de…** — versión y aviso legal.

## 5. Cosas para tener en cuenta

- El portal permite **una nota por expediente y por día**. Re-correr el mismo día
  es inofensivo: los que ya tienen nota devuelven "ya tenía".
- La tarea corre **con la sesión de Windows iniciada** (aunque estés con batería).
  Si la máquina está apagada a esa hora, no corre.
- Si alguna vez el portal pide **captcha** en una corrida automática, la app
  **no inventa nada**: frena y lo anota. Volvé a abrir la app y hacé
  **"Probar login"** para renovar la sesión.

## 6. Tu contraseña

Se guarda en el **Administrador de credenciales de Windows** (cifrado por tu
usuario), nunca en texto plano. Nadie más que vos (en tu sesión de Windows) puede
leerla.

## 7. ¿Algo no anda? (soporte)

Abrí una terminal donde está el `.exe` y corré:

```
ScoutPJN-DejarNotas.exe --check
```

Te dice si el navegador embebido y el almacén de credenciales funcionan. Pasale
ese resultado (y el `app.log`) a quien te compartió la app.
