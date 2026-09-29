# Maestro de trabajadores en Render

`data/employees.json` contiene datos personales y por seguridad permanece en `.gitignore`.

Para Render se usa un **Secret File** llamado `employees.json`. El servicio busca por defecto `/etc/secrets/employees.json`. Si el almacenamiento efímero arranca vacío, Nómina AI restaura el maestro automáticamente desde ese archivo.

No subir `employees.json` a GitHub.

Variable opcional: `EMPLOYEE_BOOTSTRAP_FILE=/etc/secrets/employees.json`.
