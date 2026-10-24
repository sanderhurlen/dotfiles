export type DraftComment = { where: string; text: string; isSkipped: boolean }
export type Draft = { id: number; line: string; isPosted: boolean; vote: string; comments: DraftComment[] }

declare module 'claude-code' {
  interface PluginState {
    'pr-utkast': { pr: number | null; draft: Shaped<Draft | null>; isConfirming: boolean }
  }
}
