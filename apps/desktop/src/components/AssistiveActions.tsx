import React, { useState } from "react";
import { cameraApi, ApiError } from "../services/cameraApi";

interface Props { disabled: boolean; }

export const AssistiveActions: React.FC<Props> = ({ disabled }) => {
  const [result, setResult] = useState("क्यामेरा सुरु गरेर विकल्प छान्नुहोस्।");
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<{ text?: string; message?: string | null; denomination?: number | null; identity?: string | null }>) => {
    setBusy(true);
    try {
      const response = await action();
      setResult(response.text || response.message || (response.denomination ? `रु ${response.denomination}` : response.identity || "निश्चित परिणाम आएन।"));
    } catch (error) {
      setResult(error instanceof ApiError ? error.message : "अनुरोध पूरा हुन सकेन।");
    } finally { setBusy(false); }
  };
  return <section className="assistive-actions" aria-labelledby="assistive-actions-title">
    <h2 id="assistive-actions-title">सहायक कार्यहरू</h2>
    <div className="detection-toolbar">
      <button className="btn btn-outline" disabled={disabled || busy} onClick={() => run(() => cameraApi.queryScene("के छ?"))}>के छ?</button>
      <button className="btn btn-outline" disabled={disabled || busy} onClick={() => run(() => cameraApi.identifyCurrency())}>नोट चिन्नुहोस्</button>
      <button className="btn btn-outline" disabled={disabled || busy} onClick={() => run(() => cameraApi.readText())}>पढ्नुहोस्</button>
      <button className="btn btn-outline" disabled={disabled || busy} onClick={() => run(() => cameraApi.recognizeFace())}>चिनजानको अनुहार</button>
    </div>
    <p className="assistive-result" role="status" aria-live="polite">{busy ? "प्रक्रिया हुँदैछ…" : result}</p>
  </section>;
};
