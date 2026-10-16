/** Browser recording/document URIs stay browser Blobs. Native resolves .native.ts. */
export async function appendUploadFile(form: FormData, uri: string, name: string, type: string): Promise<void> {
  const response = await fetch(uri);
  if (!response.ok) throw new Error('UPLOAD_FILE_READ_FAILED');
  const blob = await response.blob();
  form.append('file', blob.type === type ? blob : blob.slice(0, blob.size, type), name);
}
