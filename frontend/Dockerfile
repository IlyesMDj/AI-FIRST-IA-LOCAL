FROM node:22-alpine AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
WORKDIR /app
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next-prod ./.next-prod
COPY --from=build /app/scripts ./scripts
COPY --from=build /app/next.config.mjs ./
USER node
EXPOSE 3000
CMD ["node", "scripts/run-next.mjs", "start", "-p", "3000", "-H", "0.0.0.0"]
