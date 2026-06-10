import type { ServerResponse } from "node:http";

export type JsonErrorBody = {
  error: {
    code: string;
    message: string;
  };
};

export function sendJson(res: ServerResponse, statusCode: number, data: unknown): void {
  const body = JSON.stringify(data);
  res.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

export function sendError(res: ServerResponse, statusCode: number, code: string, message: string): void {
  const body: JsonErrorBody = { error: { code, message } };
  sendJson(res, statusCode, body);
}

export async function parseJsonBody(req: { headers: Record<string, string | string[] | undefined> } & NodeJS.ReadableStream): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      if (chunks.length === 0) {
        resolve(undefined);
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf-8")));
      } catch (err) {
        reject(new Error("Invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}
