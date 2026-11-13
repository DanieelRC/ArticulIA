# Compila la interfaz y la sirve con nginx, que además redirige /api a FastAPI.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
# Enlace al repositorio que muestra la portada (opcional).
ARG VITE_GITHUB_URL=""
ENV VITE_GITHUB_URL=$VITE_GITHUB_URL
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
