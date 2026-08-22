/**
 * Снимок из камеры или галереи → квадратное фото профиля.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Эта подготовка нужна в двух местах — в онбординге и на экране профиля, —
 * и ровно поэтому она однажды разъехалась. Копии были почти одинаковые, но в профиле вызов стоял
 * как `ImageManipulator.manipulate(...)`, а такого экспорта у модуля нет: он отдаёт класс
 * `ImageManipulator` со статическим `manipulate`. Обёртки try/catch там тоже не было, поэтому
 * человек нажимал «Изменить фото», выбирал снимок — и не получал ни фото, ни ошибки.
 *
 * Одна функция вместо двух копий, чтобы следующая правка не могла попасть только в одну из них.
 *
 * ЧТО ДЕЛАЕТ. Вырезает центральный квадрат по размерам, которые пикер отдаёт вместе с файлом
 * (системный экран «ОБРЕЗАТЬ» между выбором и профилем не нужен), ужимает до 512 и отдаёт data-URL.
 * Ужимать обязательно ДО отправки: сервер режет всё тяжелее 600 КБ, и снимок с камеры не пролезает.
 */
import * as ImageManipulator from 'expo-image-manipulator';

export type PickedImage = { uri: string; width?: number; height?: number };

export type SquarePhoto = {
  /** `data:image/jpeg;base64,…` — то, что уходит на сервер и рисуется на экране. */
  dataUrl: string;
  /** Файл на устройстве. Нужен там, где картинку показывают из ленты сообщений. */
  uri: string;
};

export async function squarePhoto(a: PickedImage): Promise<SquarePhoto> {
  const ctx = ImageManipulator.ImageManipulator.manipulate(a.uri);

  const w = Number(a.width || 0);
  const h = Number(a.height || 0);
  if (w > 0 && h > 0 && w !== h) {
    const side = Math.min(w, h);
    ctx.crop({
      originX: Math.round((w - side) / 2),
      originY: Math.round((h - side) / 2),
      width: side,
      height: side,
    });
  }

  const img = await ctx.resize({ width: 512, height: null }).renderAsync();
  const out = await img.saveAsync({
    compress: 0.75,
    format: ImageManipulator.SaveFormat.JPEG,
    base64: true,
  });

  return {
    dataUrl: out.base64 ? `data:image/jpeg;base64,${out.base64}` : out.uri,
    uri: out.uri,
  };
}
