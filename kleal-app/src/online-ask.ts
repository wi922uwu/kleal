/**
 * «СПРОСИ ШАР» — Буди на вкладке «Онлайн» (владелец 17.10.2026: «подвязать с ИИшкой, инновационно и
 * интерактивно»).
 *
 * Человек спрашивает словами — Буди отвечает движением шара: страны с подходящими затеями горят
 * (вес 0..1), шар доворачивает к лучшей, карточка говорит, почему вам по пути, и даёт первое
 * сообщение на языке собеседника с переводом. Сервер — services/buddy/online_ask.py
 * (/api/buddy/online-ask и /online-opener); на вход уходит то, что уже стоит на шаре.
 *
 * ПЕРВОЕ СООБЩЕНИЕ ЖДЁТ В ЧАТЕ. Приглашение текста не несёт (это заявка, а не письмо), поэтому
 * сообщение кладётся здесь, у себя, и подставляется в поле ввода, когда собеседник ответит и
 * откроется переписка (conversation.tsx → takeOpener). Отправляет его человек сам.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';
import { replyLang } from './i18n';
import type { OnlineIntentItem } from './online-intent-globe';

export type AskMatch = {
  id: string;
  countryCode: string;
  why: string;
  opener: string;
  openerTr: string;
  openerLang: string;
};

export type AskResult = {
  reply: string;
  matches: AskMatch[];
  countries: Record<string, number>;
  refused?: boolean;
  source?: 'model' | 'words' | 'none';
};

const wire = (it: OnlineIntentItem) => ({
  id: it.id, countryCode: it.countryCode || '', title: it.title, topics: it.topics,
  when: it.when, format: it.format, mode: it.mode,
});

export async function askGlobe(question: string, items: OnlineIntentItem[], profile: Record<string, unknown>): Promise<AskResult> {
  const r: any = await api.post('/api/buddy/online-ask', {
    question, items: items.slice(0, 60).map(wire), profile, lang: replyLang(),
  });
  return {
    reply: String(r?.reply || ''),
    matches: Array.isArray(r?.matches) ? r.matches : [],
    countries: r?.countries && typeof r.countries === 'object' ? r.countries : {},
    refused: !!r?.refused,
    source: r?.source,
  };
}

export async function rerollOpener(question: string, item: OnlineIntentItem, profile: Record<string, unknown>, previous: string) {
  const r: any = await api.post('/api/buddy/online-opener', {
    question, item: wire(item), profile, previous, lang: replyLang(),
  });
  return { opener: String(r?.opener || ''), openerTr: String(r?.openerTr || ''), openerLang: String(r?.openerLang || '') };
}

// ===== первое сообщение, отложенное до ответа собеседника

const KEY = 'kleal.opener.v1';
/** Две недели: дольше приглашение не живёт, и черновик к нему уже чужой. */
const TTL = 14 * 24 * 3600 * 1000;
type Peer = { name: string; id?: string };
const peerKey = (p: Peer) => (p.id ? 'id:' + p.id : 'n:' + String(p.name || '').trim().toLowerCase());

async function readAll(): Promise<Record<string, { text: string; at: number }>> {
  try { return JSON.parse((await AsyncStorage.getItem(KEY)) || '{}') || {}; } catch { return {}; }
}

export async function saveOpener(peer: Peer, text: string) {
  const t = String(text || '').trim();
  if (!t || !peer.name) return;
  const all = await readAll();
  const now = Date.now();
  for (const k of Object.keys(all)) if (now - (all[k]?.at || 0) > TTL) delete all[k];
  all[peerKey(peer)] = { text: t, at: now };
  if (peer.id) all[peerKey({ name: peer.name })] = { text: t, at: now };
  try { await AsyncStorage.setItem(KEY, JSON.stringify(all)); } catch { /* черновик — не данные */ }
}

/** Забрать черновик для переписки: отдаётся один раз. */
export async function takeOpener(peer: Peer): Promise<string> {
  const all = await readAll();
  const keys = [peer.id ? peerKey(peer) : '', peerKey({ name: peer.name })].filter(Boolean);
  const hit = keys.map((k) => all[k]).find((v) => v && Date.now() - v.at <= TTL);
  if (!hit) return '';
  for (const k of keys) delete all[k];
  try { await AsyncStorage.setItem(KEY, JSON.stringify(all)); } catch { /* ничего */ }
  return hit.text;
}

// ===== значок темы для онлайн-затеи

/*
 * Темы онлайн-затей приходят словами автора («chess», «valorant»), а не ключами реестра, и
 * iconNameFor по ним молчит — плитка темы рисовала точку. Сначала реестр, потом слово по корню;
 * не узнали — значок «сообщество», а не пустота.
 */
const TOPIC_WORDS: [RegExp, string][] = [
  [/chess|xadrez|scacc|ajedrez|шахмат|board ?game|настол/i, 'boardgames'],
  [/valorant|minecraft|game|gaming|dota|cs2|fortnite|игр|jogo|gioc|juego/i, 'gaming'],
  [/english|language|idiom|lingu|japanese|spanish|french|german|язык|англ|exchange|intercambio/i, 'languages'],
  [/code|coding|react|program|dev|python|startup|пет-проект|код/i, 'coding'],
  [/book|read|lectur|livro|libro|книг|чтени/i, 'books'],
  [/draw|dibuj|desen|paint|art|рис/i, 'visualart'],
  [/music|guitar|piano|музык|песн/i, 'music'],
  [/movie|film|cinema|кино|serie/i, 'cinema'],
  [/yoga|meditat|fitness|workout|йог|трен/i, 'fitness'],
];

export function topicIcon(topics: readonly string[], iconNameFor: (k: string) => string): string {
  for (const t of topics) { const n = iconNameFor(t); if (n) return n; }
  const all = topics.join(' ');
  for (const [re, name] of TOPIC_WORDS) if (re.test(all)) return name;
  return 'community';
}
