export type DraftComment = { where: string; text: string; isSkipped: boolean }
export type Draft = {
  id: number
  repo: string
  line: string
  isPosted: boolean
  vote: string
  comments: DraftComment[]
}
export type Pr = { id: number; repo: string }

declare module 'claude-code' {
  interface PluginState {
    'pr-utkast': {
      prs: Shaped<Pr[]>
      drafts: Shaped<Draft[]>
      confirming: number | null
      paneFor: number | null
    }
  }
}
