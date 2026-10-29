export const steps = [
  ['Sign in', 'Open the Windows application and sign in with Google through your system browser.'],
  ['Choose the source', 'Explicitly select a monitor or an eligible application window. Region capture is not available.'],
  ['Capture the question', 'Take one frame. Review the preview, retake it or change the source. Nothing is captured continuously.'],
  ['Read Question', 'Choose Read Question to send the selected image to OpenAI for a structured observation. Review the text, options and reading confidence.'],
  ['Get Suggested Answer', 'Choose a reasoning mode and explicitly request a recommendation. Grounded modes use only selected materials and require passage-transmission consent.'],
  ['Review and learn', 'Read the suggested answer and educational explanation. Inspect any applicable source passages. Estimates can be wrong; check important conclusions.'],
] as const
export const modes = [
  ['01','General','A broader perspective.','Uses model knowledge without retrieving your Context Library documents. No materials required.'],
  ['02','Context Guided','Your references, in focus.','Uses relevant passages from selected documents, with general model reasoning clearly distinguished from document support.'],
  ['03','Materials Only','Evidence sets the boundary.','Uses selected evidence and abstains when it cannot support a reliable answer. Inspect citations and review the source.'],
] as const
