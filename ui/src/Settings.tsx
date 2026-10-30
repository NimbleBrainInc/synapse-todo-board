import { useEffect, useState } from "react";
import { useApp } from "@nimblebrain/synapse/react";
import { AppFrame, Button, Card, Heading, Inline, Spinner, Stack, Text } from "@nimblebrain/synapse/ui";
import { inputStyle } from "./formStyles";
import { useStyleTokens } from "./tokens";

const MAX_BYTES = 8 * 1024;

export default function Settings() {
  const app = useApp();
  const t = useStyleTokens();
  const [text, setText] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let active = true;
    void app.readServerResource({ uri: "app://instructions" }).then((result) => {
      const content = result.contents.find((item) => "text" in item && typeof item.text === "string");
      if (!content || !("text" in content) || typeof content.text !== "string") throw new Error("The instructions resource did not return text.");
      if (active) {
        setText(content.text);
        setSaved(content.text);
        setLoaded(true);
      }
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : "Could not load instructions.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [app]);

  const bytes = new TextEncoder().encode(text).length;
  const overLimit = bytes > MAX_BYTES;

  async function save() {
    if (overLimit || loading || !loaded || saving) return;
    setSaving(true);
    setError(null);
    setStatus("");
    try {
      const result = await app.callTool<{ status: string; error?: string }>("set_custom_instructions", { text });
      if (result.isError || result.data?.status === "error") {
        throw new Error(result.data?.error || "Could not save instructions.");
      }
      if (!["saved", "cleared"].includes(result.data?.status)) throw new Error("The server did not confirm the change.");
      setSaved(text);
      setStatus(text ? "Saved" : "Cleared");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save instructions.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppFrame contentWidth="reading">
      <AppFrame.Header>
        <Heading size="sm">Custom instructions</Heading>
      </AppFrame.Header>
      <AppFrame.Body>
        {loading ? <Inline gap="0.5rem"><Spinner /><Text>Loading instructions</Text></Inline> : loaded ? (
          <Card>
            <Stack gap="1rem">
              <Text>Save guidance the agent should use with Todo Board. Clear the text to remove it.</Text>
              <label htmlFor="custom-instructions"><Text size="sm" weight="medium">Instructions</Text></label>
              <textarea
                id="custom-instructions"
                value={text}
                onChange={(event) => { setText(event.target.value); setStatus(""); }}
                disabled={saving}
                style={{ ...inputStyle(t), minHeight: "12rem", resize: "vertical" }}
              />
              <Inline gap="0.5rem" style={{ flexWrap: "wrap" }}>
                <Button onClick={() => void save()} disabled={saving || overLimit || text === saved}>Save</Button>
                <Button variant="secondary" disabled={saving || text === saved} onClick={() => { setText(saved); setStatus(""); }}>Reset</Button>
                <Text size="sm" tone={overLimit ? "danger" : "muted"} style={{ marginLeft: "auto" }}>{bytes.toLocaleString()} / {MAX_BYTES.toLocaleString()} bytes</Text>
              </Inline>
              {status && <Text role="status" tone="success">{status}</Text>}
            </Stack>
          </Card>
        ) : null}
        {error && <Text as="p" role="alert" tone="danger">{error}</Text>}
      </AppFrame.Body>
    </AppFrame>
  );
}
