# Tickets API

Servicio local en Python para registrar tickets de soporte, consultarlos y enviarlos a un proveedor simulado.

El alcance es: **tres endpoints**, SQLite en archivo y un proveedor en proceso.

## Stack

- Python 3.11+ (probado con Python 3.14).
- FastAPI + Pydantic v2.
- SQLite mediante `sqlite3` de la librería estándar.
- pytest + `TestClient` para los tests.

## Estructura

```text
app/
  api/tickets.py              # Endpoints HTTP
  models/ticket.py            # Ticket y TicketStatus
  schemas/ticket.py           # TicketCreate y TicketOut
  services/ticket_service.py  # Reglas de negocio y transición de estado
  repositories/
    ticket_repository.py      # SQL de tickets
  providers/
    mock_provider.py          # Proveedor simulado e inyectable
  db.py                       # Conexión e inicialización de SQLite
  main.py                     # Composición de la aplicación

tests/
  conftest.py
  test_db.py
  test_tickets_api.py
  test_ticket_service.py
  test_ticket_send.py
  test_mock_provider.py
```

## Instalación

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

En Linux/macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Base de datos

No hace falta ejecutar un comando de inicialización: la tabla se crea de forma idempotente al construir la aplicación, mediante `CREATE TABLE IF NOT EXISTS`.

- Ruta por defecto: `tickets.db` en el directorio desde el que se arranca la API.
- Ruta configurable:

```powershell
$env:TICKETS_DB_PATH = "C:\ruta\abai-tickets.db"
```

- Para reiniciar los datos de desarrollo, detén la API y elimina el fichero `tickets.db`.
- No hay migraciones. Si cambia el esquema, hay que recrear la base local.

La tabla `tickets` guarda `id`, `subject`, `description`, `email`, `status`, `created_at` y `external_id`. Además de las restricciones de la aplicación, SQLite comprueba que `status` solo sea `pending` o `sent` y que `external_id` sea nulo únicamente en estado `pending`.

## Arranque

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Tests

```powershell
.\.venv\Scripts\pytest.exe -q
```

Alternativa:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Última ejecución verificada: **53 tests pasando**.

## Ejemplos

### Crear un ticket

```powershell
curl.exe -i -X POST "http://127.0.0.1:8000/tickets" `
  -H "Content-Type: application/json" `
  -d '{"subject":"No puedo acceder","description":"La aplicación devuelve un error.","email":"user@example.com"}'
```

Respuesta esperada: **201**

```json
{
  "id": "3b4705d3-ed5c-475e-adca-52a28a7c4fa6",
  "subject": "No puedo acceder",
  "description": "La aplicación devuelve un error.",
  "email": "user@example.com",
  "status": "pending",
  "created_at": "2026-10-27T17:25:34.809869Z",
  "external_id": null
}
```

### Consultar un ticket

Sustituye `<TICKET_ID>` por el `id` devuelto:

```powershell
curl.exe -i "http://127.0.0.1:8000/tickets/<TICKET_ID>"
```

Respuesta esperada: **200** con el ticket persistido, o **404** si no existe.

### Enviar un ticket

```powershell
curl.exe -i -X POST "http://127.0.0.1:8000/tickets/<TICKET_ID>/send"
```

Con el modo por defecto (`success`), la respuesta es **200**:

```json
{
  "id": "3b4705d3-ed5c-475e-adca-52a28a7c4fa6",
  "subject": "No puedo acceder",
  "description": "La aplicación devuelve un error.",
  "email": "user@example.com",
  "status": "sent",
  "created_at": "2026-10-27T17:25:34.809869Z",
  "external_id": "ext_3b4705d3-ed5c-475e-adca-52a28a7c4fa6"
}
```

Un segundo envío del mismo ticket devuelve **200** con el mismo registro y **no llama de nuevo al proveedor**.

## Modos del proveedor simulado

El modo se configura con la variable de entorno `PROVIDER_MODE` al arrancar la aplicación. El valor por defecto es `success`.

| Modo | Comportamiento | HTTP en `POST /send` | Estado final |
|---|---|---|---|
| `success` | Devuelve `ext_<ticket_id>` | 200 | `sent`, con `external_id` |
| `timeout` | Lanza `ProviderTimeoutError` sin esperar | 504 | `pending`, `external_id=null` |
| `error` | Lanza `ProviderUnavailableError` | 502 | `pending`, `external_id=null` |

Ejemplo para probar timeout en PowerShell:

```powershell
$env:PROVIDER_MODE = "timeout"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Detén el proceso y vuelve a arrancar con `PROVIDER_MODE=success` para comprobar que el mismo ticket pendiente puede enviarse correctamente. El modo se lee al construir la aplicación; cambiarlo requiere reiniciar.

Para probar indisponibilidad:

```powershell
$env:PROVIDER_MODE = "error"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

En los tests no se depende de variables de entorno: se inyecta un proveedor espía mediante `create_app(..., provider=...)`, lo que permite contar llamadas y cambiar el modo de forma controlada.

## Contrato HTTP

| Método | Ruta | Éxito | Errores |
|---|---|---|---|
| `POST` | `/tickets` | 201 + ticket completo | 422 por validación, campos faltantes o campos gestionados |
| `GET` | `/tickets/{id}` | 200 + ticket persistido | 404 si no existe |
| `POST` | `/tickets/{id}/send` | 200 + ticket (enviado o ya enviado) | 404 inexistente; 500 error interno; 504 timeout; 502 proveedor no disponible |

Las respuestas de error controladas tienen la forma `{"detail": "..."}`. Los errores de validación usan el formato estándar de FastAPI/Pydantic.

## Validación y decisiones

- **422** para toda entrada inválida. El enunciado permitía 400 o 422; se elige 422 por consistencia con Pydantic y FastAPI.
- **`extra="forbid"`**: el cliente no puede fijar `id`, `status`, `created_at` ni `external_id`; cualquier campo extra se rechaza.
- **Trim antes de validar y persistir**: subject y description se recortan por los extremos; los saltos de línea internos se conservan. Los límites son 1–120 y 1–2000 caracteres.
- **EmailStr**: se valida sintaxis con `email-validator`; no se comprueba que el buzón exista ni se consultan registros MX.
- **UUID4** generado por el backend para evitar enumeración.
- **`created_at`** se genera con `datetime.now(UTC)` y se serializa como ISO-8601 con sufijo `Z`.
- **El id del path es opaco**: un id inexistente o con formato no UUID devuelve 404, no 422.
- **SQLite sin ORM**: una sola tabla no justifica una capa extra; el SQL queda explícito y es fácil de inspeccionar. Cada operación abre y cierra su propia conexión.

## Flujo de envío

```text
pending --success--> sent
   |
   +--timeout/error--> pending (sin cambios)
```

1. Se busca el ticket; si no existe, 404.
2. Si ya está `sent`, se devuelve el registro actual sin llamar al proveedor.
3. Si está `pending`, se llama al proveedor.
4. Solo después de un resultado satisfactorio se ejecuta la actualización SQL que guarda `status=sent` y `external_id`.
5. Timeout y proveedor no disponible no modifican la fila; el cliente puede reintentar manualmente.

No hay reintentos automáticos ni cola de trabajo.

## Idempotencia y limitaciones

### Idempotencia secuencial

Está implementada y cubierta por tests: si un ticket ya está `sent`, un nuevo `POST /send` devuelve 200 con el mismo ticket y no invoca al proveedor. El test usa un espía y comprueba que el número de llamadas no aumenta.

### Concurrencia

No se implementa un lock distribuido ni una garantía de idempotencia concurrente.

Dos peticiones simultáneas pueden leer el ticket como `pending` y ambas llamar al proveedor. La actualización usa `WHERE status = 'pending'` para no sobrescribir un `external_id` ya guardado, pero eso no elimina la posible llamada duplicada al sistema externo. Una solución completa requeriría bloqueo por fila, una clave de idempotencia o una cola de outbox.

### Proveedor acepta, persistencia local falla

Si el proveedor responde correctamente pero la escritura posterior en SQLite falla, la excepción de persistencia se propaga, la API responde **500** y el ticket permanece `pending`. No se devuelve un 200 engañoso. El proveedor externo ya podría haber registrado el envío, por lo que un reintento manual podría duplicarlo.

Esta situación no se resuelve en la implementación actual. Para reducir el riesgo de envíos duplicados, podría utilizarse una clave de idempotencia admitida por el proveedor y registrarse cada intento de envío.

## Logging

El logger `abai.tickets` registra únicamente el id del ticket y el resultado de la operación (`created`, `sent`, `timeout`, `unavailable`, `already_sent`). No se registran email, subject ni description.

## Tests incluidos

- Alta válida y consulta posterior.
- Validaciones de subject, description, email, campos faltantes y campos gestionados.
- Persistencia tras reiniciar la aplicación.
- Envío correcto: 200, `status=sent` y `external_id` persistido.
- Envío a ticket inexistente: 404 sin llamar al proveedor.
- Timeout: 504 y ticket intacto.
- Proveedor no disponible: 502 y ticket intacto.
- Reintento después de timeout o error: el mismo ticket termina en `sent`.
- Segundo envío secuencial: mismo registro y sin segunda llamada al proveedor.
- Errores inesperados del proveedor no se convierten en 502/504 y responden 500.
- Un fallo al persistir el resultado del proveedor responde 500 y deja el ticket `pending`.


## Tiempo y uso de IA

- **Uso de IA:** Se utilizó ChatGPT como apoyo para el análisis y OpenCode para la implementación y revisión. El código se ejecutó con la suite de tests y se realizó una comprobación manual con Uvicorn.
- **Código reutilizado:** no se copió código de terceros; se siguieron patrones de la documentación oficial de FastAPI, Pydantic y SQLite.

| Bloque | Tiempo estimado | Entregable |
|---|---:|---|
| Análisis y diseño | ~30 min | Contratos, estructura y decisiones técnicas |
| API y persistencia | ~95 min | `POST /tickets`, `GET /tickets/{id}`, SQLite, modelos, schemas y repositorio |
| Proveedor y errores | ~40 min | `MockProvider`, `POST /send`, 502/504, transición de estado e idempotencia secuencial |
| Tests | ~45 min | Suite final de 53 tests |
| README y verificación | ~30 min | Documentación, smoke tests y revisión final |
| **Total** | **240 min** | **API completa y suite verificada** |
