FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tailwind.config.js postcss.config.js components.json ./
COPY src ./src
RUN npm run build

FROM nginx:alpine AS runner

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
