import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts, Fraunces_600SemiBold } from '@expo-google-fonts/fraunces';
import {
  PlusJakartaSans_400Regular,
  PlusJakartaSans_700Bold,
} from '@expo-google-fonts/plus-jakarta-sans';
import { colors } from './src/theme';
import { ReferralScreen } from './src/app/ReferralScreen';

export default function App() {
  const [fontsLoaded] = useFonts({
    Fraunces_600SemiBold,
    PlusJakartaSans_400Regular,
    PlusJakartaSans_700Bold,
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
