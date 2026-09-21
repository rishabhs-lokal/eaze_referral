import Constants from 'expo-constants';

// Reads EXPO_PUBLIC_API_BASE_URL from the environment (see .env.example), falling back to the
// local backend dev server started via `npm run dev` in eaze-referral-backend/.
export const API_BASE_URL: string =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  'http://localhost:4000';
