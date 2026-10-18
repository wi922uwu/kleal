/**
 * Знак ChatGPT для чипа «Через ChatGPT» (18.10.2026).
 *
 * Официальный монохромный знак OpenAI из их брендбука (openai.com/brand): без искажений и без
 * перекраски в наш коралл — так требуют правила бренда. Источник — архив
 * cdn.openai.com/brand/openai-logos.zip (OAI_OpenAI-Blossom_Black.png, скачан 18.10.2026 с разрешения
 * Ивана); пустое поле вокруг знака обрезано, размер уменьшен до 96 px — цвет и пропорции не тронуты.
 */
import { Image } from 'react-native';

const MARK = require('../../assets/brand/chatgpt-mark.png');

export function ChatGPTMark({ size = 16 }: { size?: number }) {
  return <Image accessibilityIgnoresInvertColors source={MARK} style={{ width: size, height: size }} resizeMode="contain" />;
}
