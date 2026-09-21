import 'dotenv/config';
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';
import { pool } from './db';

async function main() {
  const dir = join(__dirname, '..', 'migrations');
  const files = readdirSync(dir).filter((f) => f.endsWith('.sql')).sort();
  for (const file of files) {
    const sql = readFileSync(join(dir, file), 'utf8');
    console.log(`Running migration: ${file}`);
    await pool.query(sql);
  }
  console.log('Migrations complete.');
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
