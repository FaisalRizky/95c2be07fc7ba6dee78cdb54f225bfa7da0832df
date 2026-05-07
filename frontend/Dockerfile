# Build stage
FROM node:20-slim AS build-stage

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the TypeScript code
RUN npm run build

# Production stage
FROM nginx:stable-alpine

# Copy built assets from build-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Install as a template — the official nginx Docker image entrypoint runs
# envsubst on every file in /etc/nginx/templates/ at container start, writing
# the result to /etc/nginx/conf.d/. Only env vars actually present in the
# container environment are substituted (nginx's $host, $uri etc. are safe).
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
