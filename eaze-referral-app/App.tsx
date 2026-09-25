import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts, Fraunces_600SemiBold } from '@expo-google-fonts/fraunces';
import {
  PlusJakartaSans_400Regular,
  PlusJakartaSans_400Regular_Italic,
  PlusJakartaSans_700Bold,
  PlusJakartaSans_700Bold_Italic,
} from '@expo-google-fonts/plus-jakarta-sans';
import { colors } from './src/theme';
import { ReferralScreen } from './src/app/ReferralScreen';

export default function App() {
  const [fontsLoaded] = useFonts({
    Fraunces_600SemiBold,
    PlusJakartaSans_400Regular,
    PlusJakartaSans_700Bold,
    // The invite message card's bold-italic style (CopyableMessageCard.tsx) and the phone-field
    // legal disclaimer (ReferralScreen.tsx) each need their own font file — RN doesn't reliably
    // synthesize italic/bold slanting for a custom static font on native the way a browser would
    // for CSS font-style/font-weight on an unmatched file.
    PlusJakartaSans_700Bold_Italic,
    PlusJakartaSans_400Regular_Italic,
  });

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.base.black100, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.primary[500]} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <ReferralScreen />
      <StatusBar style="light" />
    </SafeAreaProvider>
  );
}
