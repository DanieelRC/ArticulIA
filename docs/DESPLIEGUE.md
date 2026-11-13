# Despliegue en un VPS

Guía para publicar ArticulIA con HTTPS y con el gasto en el LLM acotado.

## Requisitos
- VPS con Docker y Docker Compose. Recomendado: 4 vCPU y 8 GB de RAM (los modelos de
  embeddings y reranker corren en CPU y ocupan unos 3 GB en memoria).
- Un dominio o subdominio con un registro A apuntando a la IP del VPS.
- Puertos 80 y 443 abiertos en el firewall. **No abras** 5432, 8000 ni 3000.

## Pasos
1. Clona el repositorio en el VPS y crea `.env` a partir de `.env.example`.
2. En `.env` define, como mínimo:

   ```bash
   DOMINIO=articulia.tudominio.com
   POSTGRES_PASSWORD=<una contraseña larga y única>
   LLM_PROVIDER=xai
   LLM_MODEL=grok-build-0.1
   XAI_API_KEY=<tu clave>
   DAILY_BUDGET_USD=1.0
   ```

3. Lleva el corpus indexado. Lo más rápido es exportar la base desde tu equipo y restaurarla,
   porque indexar tarda unos 40 minutos en CPU:

   ```bash
   # en tu equipo
   docker exec articulia-db pg_dump -U articulia -Fc articulia > articulia.dump
   # en el VPS, con la base ya levantada
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db
   docker exec -i articulia-db pg_restore -U articulia -d articulia --clean --if-exists < articulia.dump
   ```

4. Levanta todo:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

   La primera vez la API descarga los modelos de Hugging Face (varios GB) al volumen
   `hf_models`; la portada responde de inmediato y las preguntas en cuanto termina la carga.
5. Verifica: `https://<DOMINIO>/` carga con candado, `https://<DOMINIO>/api/health` responde
   `{"status":"ok","db":true}` y `https://<DOMINIO>/api/docs` da 404.

## Qué protege tu saldo
| Barrera | Dónde | Valor por defecto |
| --- | --- | --- |
| Límite de gasto mensual del proveedor | Consola de xAI | **Configúralo tú**: es la única barrera que no depende de este servidor |
| Tope de gasto diario | API (`DAILY_BUDGET_USD`) | 1 USD; al alcanzarlo, `/ask` responde 429 hasta el día siguiente (UTC) |
| Límite por IP | nginx y API (`RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_DAY`) | 5 por minuto y 30 por día |
| Caché de respuestas | API (`ANSWER_CACHE_TTL_HOURS`) | 7 días; la misma pregunta no vuelve a pagar |
| Tope por consulta | API (`LLM_MAX_OUTPUT_TOKENS`, `MAX_TOKENS_PER_QUERY`) | 4,000 de salida por llamada y 40,000 por consulta |
| Concurrencia | API (`MAX_CONCURRENT_AGENTS`) | 2 consultas a la vez |

El gasto se calcula con `LLM_PRICE_IN_PER_M` y `LLM_PRICE_OUT_PER_M` (USD por millón de
tokens). **Si cambias de modelo, actualiza esos precios**, o el tope diario contará mal.

Para ver el gasto acumulado:

```bash
docker exec articulia-db psql -U articulia -c "SELECT * FROM usage_daily ORDER BY day DESC LIMIT 7"
```

## Qué queda cerrado
- Solo Caddy publica puertos. La base, la API y nginx viven en la red interna de Compose.
- `ENVIRONMENT=production` apaga `/docs`, `/redoc` y `/openapi.json`.
- La API corre como usuario sin privilegios dentro del contenedor.
- nginx envía cabeceras de seguridad (CSP, `nosniff`, `X-Frame-Options`) y Caddy agrega HSTS.
- Las fuentes se sirven desde el propio sitio: el navegador del visitante no contacta a terceros.

## Limitaciones conocidas
- El límite por IP de la API vive en memoria: se reinicia si se reinicia el contenedor. El tope
  diario de gasto sí persiste, en PostgreSQL.
- Varias personas detrás de una misma IP (una oficina) comparten el límite por IP.
- No hay cuentas de usuario ni CAPTCHA: quien rote de IP puede hacer más preguntas, pero nunca
  más allá del tope diario de gasto.
