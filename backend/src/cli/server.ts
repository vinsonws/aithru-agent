import { createApp } from "../api/app.js";

async function main() {
  const app = await createApp();

  const port = parseInt(process.env.PORT || "8000", 10);
  const host = process.env.HOST || "0.0.0.0";

  try {
    await app.listen({ port, host });
    console.log(`Aithru Agent (TypeScript) listening on http://${host}:${port}`);
    console.log(`Health check: http://localhost:${port}/api/health`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

main();
