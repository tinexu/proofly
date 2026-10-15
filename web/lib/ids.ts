// Unguessable IDs and tokens (spec: no guessable public case IDs, random scoped tokens).
const ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789";

export function randomId(length = 16): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let out = "";
  for (const b of bytes) out += ALPHABET[b % ALPHABET.length];
  return out;
}