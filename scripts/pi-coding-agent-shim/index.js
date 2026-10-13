export * from "/home/sab-mini/.local/share/pi/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js";

// pi 0.87.1 does not export this. pi-extensible-workflows 6.2.0 imports it.
// The GDAD host never calls it; shell and checkpoint are the bridges we use.
export function createCodemodeExtension() {
  return undefined;
}
export function createMcpExtension() {
  return undefined;
}
export function createToolSearchExtension() {
  return undefined;
}
