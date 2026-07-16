FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

# Dev server is sufficient for Week 1 foundation scaffold.
CMD ["npm", "run", "dev"]
