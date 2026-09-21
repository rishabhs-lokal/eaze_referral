import { Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';

// Web: some embedding contexts (iframes with a restrictive Permissions-Policy, non-focused
// tabs) deny navigator.clipboard.writeText even from a real click. Fall back to the older
// execCommand('copy') path, which works in more of those cases.
async function copyOnWeb(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the execCommand fallback
  }
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

export async function copyToClipboard(text: string): Promise<boolean> {
  if (Platform.OS === 'web') return copyOnWeb(text);
  try {
    await Clipboard.setStringAsync(text);
    return true;
  } catch {
    return false;
  }
}
