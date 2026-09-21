import { Platform } from 'react-native';

export type PlatformKind = 'ios' | 'android' | 'other';

// Native builds already know their OS. For the web build — which is what actually renders
// inside the in-app banner's WebView on the referrer's phone — user-agent sniffing is the only
// signal available for telling an iOS WebView from an Android one.
export function getPlatformKind(): PlatformKind {
  if (Platform.OS === 'ios') return 'ios';
  if (Platform.OS === 'android') return 'android';
  if (Platform.OS === 'web' && typeof navigator !== 'undefined') {
    const ua = navigator.userAgent.toLowerCase();
    if (/iphone|ipad|ipod/.test(ua)) return 'ios';
    if (/android/.test(ua)) return 'android';
  }
  return 'other';
}
