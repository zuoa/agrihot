FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=80
ENV NITRO_HOST=0.0.0.0
ENV NITRO_PORT=80
ENV NUXT_API_BASE=http://backend:8000
COPY --from=build /app/.output ./.output
EXPOSE 80
CMD ["node", ".output/server/index.mjs"]
