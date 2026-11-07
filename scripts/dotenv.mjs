// Reads KEY=value lines from a .env file for the developer scripts, without printing values.
import fs from 'node:fs';

/** Parses a .env file into an object. */
export function readDotenv(file) {
  const values = {};
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/.exec(line);
    if (match) values[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  return values;
}
