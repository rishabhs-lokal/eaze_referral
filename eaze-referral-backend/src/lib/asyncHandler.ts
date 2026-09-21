import { NextFunction, Request, Response } from 'express';

// Express 4 doesn't forward rejected promises from async handlers to error middleware on its
// own — without this, a thrown query error hangs the request instead of returning a 500.
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>
) {
  return (req: Request, res: Response, next: NextFunction) => {
    fn(req, res, next).catch(next);
  };
}
