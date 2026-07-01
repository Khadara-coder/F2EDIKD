FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV MOCK_MODE=true
ENV PORT=3001

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3001/health || exit 1

CMD ["node", "dist/index.js"]
