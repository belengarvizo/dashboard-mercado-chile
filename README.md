# Dashboard de mercado chileno

Panel que consolida indicadores macroeconómicos del Banco Central de Chile
y precios de acciones del IPSA en un solo lugar, actualizado diariamente.

## Estructura del proyecto

```
dashboard-mercado-chile/
├── app/
│   └── dashboard.py          # La app de Streamlit (lo que ves en el navegador)
├── scripts/
│   ├── actualizar_bcch.py    # Descarga series del Banco Central
│   └── actualizar_acciones.py # Descarga precios de acciones vía Yahoo Finance
├── models.py                  # Define las tablas de la base de datos
├── requirements.txt           # Librerías necesarias
└── .env.example                # Plantilla de variables de entorno
```

## Cómo correrlo en local (VS Code)

1. Instala las librerías:
   ```
   py -m pip install -r requirements.txt --break-system-packages
   ```

2. Copia `.env.example` a `.env` y completa tus credenciales:
   - Credenciales del BCCh (gratis): https://si3.bcentral.cl/Siete/en/Siete/API
   - Una base de datos PostgreSQL (puedes usar una gratuita de Neon o Supabase mientras no tengas Railway conectado)

3. Crea las tablas (solo la primera vez):
   ```
   py models.py
   ```

4. Descarga los datos:
   ```
   py scripts/actualizar_bcch.py
   py scripts/actualizar_acciones.py
   ```

5. Corre el dashboard:
   ```
   streamlit run app/dashboard.py
   ```

## Despliegue en Railway

Pendiente: se configura cuando conectemos el repo de GitHub a Railway,
agregando el cron job que corre los scripts de `scripts/` una vez al día.
