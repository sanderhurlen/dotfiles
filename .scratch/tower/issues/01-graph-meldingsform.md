# Hvilke Graph-felt må mock-formatet speile?

Type: research
Status: closed
Assignee: Sander Hurlen
Blocked by:

## Question

Hvilke felt i Microsoft Graph sin `message` (mail, inkl. `conversationId`, from/to/cc, body-format, `isRead`) og Teams `chatMessage`/chat-tråd trenger tower for å vise en Tråd, triagere og svare? Og hvilke Graph-kall brukes for å svare (reply/replyAll/createReply, chat send)? Resultatet blir grunnlaget for mock-filformatet.

## Resolution

Funn: [research/graph-meldingsform.md](../research/graph-meldingsform.md) (også på branch `research/graph-meldingsform`, 43197fd).

- Mail-Tråd = meldinger med samme `conversationId`. Felt: `id`, `subject`, `from`, `toRecipients`/`ccRecipients`/`replyTo`, `receivedDateTime`, `body{contentType,content}`, `bodyPreview`, `isRead`, `importance`, `hasAttachments`, `webLink`.
- Teams-Tråd = `chat` (`id`, `chatType`, `topic`, `members`, `viewpoint.lastMessageReadDateTime`) + `chatMessage` (`id`, `chatId`, `messageType`, `createdDateTime`, `from.user`, `body`, `importance`, `mentions`). Ulest = nyere enn `lastMessageReadDateTime`. Filtrér bort `systemEventMessage`.
- Svar: mail `POST /me/messages/{id}/reply|replyAll` (202, ingen id); chat `POST /chats/{id}/messages`. Kanaltråder krever admin-consent → ute av v1.
- Mock: én JSON-fil per Tråd med ordrette Graph-objekter i `value`. Outbox-fil = eksakt request (method, path, body) ekte adapter ville sendt. "Meg"-identitet i én config-verdi.
- Åpent: ekte mail-body har sitert historikk → ekte adapter bør hente `uniqueBody`; mock antar ren ny tekst.
