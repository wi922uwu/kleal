import { File } from 'expo-file-system';

/** Expo fetch accepts a File/Blob, not React Native's old {uri, name, type} part.
 * Keep the existing wire filename and MIME without copying or renaming the recording. */
export async function appendUploadFile(form: FormData, uri: string, name: string, type: string): Promise<void> {
  const file = new File(uri);
  // These are JS multipart metadata only; the native file URI and its bytes stay unchanged.
  Object.defineProperties(file, { name: { value: name }, type: { value: type } });
  form.append('file', file);
}
