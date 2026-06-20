# syntax=docker/dockerfile:1.4
FROM node:18-alpine

WORKDIR /app

# Copy package files first so install layer is only invalidated when deps change.
COPY package.json package-lock.json* ./

# Cache mount keeps ~/.npm across rebuilds — only new/changed packages download.
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Copy application code last — code changes do not invalidate the install layer.
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]

