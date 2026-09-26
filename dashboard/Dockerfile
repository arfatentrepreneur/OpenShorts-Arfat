# Multi-stage: `dev` for local docker-compose (HMR), `prod` for Coolify/production.
# The prod stage is last, so `docker build` (and Coolify) produce the static build
# by default. Local docker-compose targets the `dev` stage explicitly.

# ---- deps + dev server (local) ----
FROM node:18-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ---- production build ----
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Vite bakes env at BUILD time. Set VITE_API_URL to the backend's public URL
# (Coolify: add it as a build variable on the frontend service). Empty = same-origin.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
# Optional product analytics (OpenPanel). Left empty, index.html initialises
# nothing and the build phones home to nobody — see the comment there.
ARG VITE_OPENPANEL_API_URL=""
ENV VITE_OPENPANEL_API_URL=$VITE_OPENPANEL_API_URL
ARG VITE_OPENPANEL_CLIENT_ID=""
ENV VITE_OPENPANEL_CLIENT_ID=$VITE_OPENPANEL_CLIENT_ID
RUN npm run build

# ---- static serving (nginx) ----
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
