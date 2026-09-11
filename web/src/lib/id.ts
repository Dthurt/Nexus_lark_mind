export function newId() {
  const gen =
    crypto.randomUUID ||
    (() => Math.random().toString(16).slice(2) + Date.now());
  return (gen as any).call(crypto).replace(/-/g, "");
}
