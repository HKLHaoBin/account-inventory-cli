import { describe, expect, it } from "vitest";
import { readHttpErrorDetail } from "./http-error";

describe("readHttpErrorDetail", () => {
  it("extracts FastAPI string detail from JSON error bodies", async () => {
    const response = new Response(
      JSON.stringify({ detail: "请先配置数据库服务地址" }),
      { status: 428, headers: { "Content-Type": "application/json" } }
    );

    await expect(readHttpErrorDetail(response)).resolves.toBe(
      "请先配置数据库服务地址"
    );
  });

  it("falls back to raw text when the body is not JSON", async () => {
    const response = new Response("upstream unavailable", { status: 502 });

    await expect(readHttpErrorDetail(response, "请求失败：502")).resolves.toBe(
      "upstream unavailable"
    );
  });
});
