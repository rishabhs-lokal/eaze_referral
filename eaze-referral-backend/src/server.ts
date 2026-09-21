import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { referralRouter } from './routes/referral';
import { redirectRouter } from './routes/redirect';

const app = express();
app.use(cors());
app.use(express.json());

app.get('/health', (_req, res) => res.json({ ok: true }));

app.use('/api/referral', referralRouter);
app.use(redirectRouter);

// Centralized error handler so a thrown query error returns 500 JSON instead of hanging/crashing.
app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error(err);
  res.status(500).json({ error: 'Internal error' });
});

const port = Number(process.env.PORT ?? 4000);
app.listen(port, () => {
  console.log(`eaze-referral-backend listening on http://localhost:${port}`);
});
