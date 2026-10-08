# Research: Graph-felt mock-formatet må speile

Ticket: `.scratch/tower/issues/01-graph-meldingsform.md`
Kilder: Microsoft Graph v1.0-referansen på learn.microsoft.com, lest 2026-10-07. Lenker står ved hver påstand.

## Svar i kort form

- **Mail-Tråd** = alle `message` med samme `conversationId`. Det tower trenger: `id`, `conversationId`, `subject`, `from`, `toRecipients`, `ccRecipients`, `replyTo`, `receivedDateTime`, `body{contentType,content}`, `bodyPreview`, `isRead`, `importance`, `hasAttachments`, `webLink`.
- **Teams-Tråd** = en `chat` (1:1/gruppe) med sine `chatMessage`. Det tower trenger: chat `id`, `chatType`, `topic`, `members`, `viewpoint.lastMessageReadDateTime`; per melding `id`, `chatId`, `messageType`, `createdDateTime`, `from.user{id,displayName}`, `body{contentType,content}`, `importance`, `mentions`.
- **Svare på mail**: `POST /me/messages/{id}/reply` eller `/replyAll` (ett kall, `Mail.Send`), eller `createReply` + `PATCH` + `send` (utkast i Outlook, `Mail.ReadWrite` + `Mail.Send`).
- **Svare i Teams-chat**: `POST /chats/{chat-id}/messages` (`ChatMessage.Send`). Kanal-tråd: `POST /teams/{t}/channels/{c}/messages/{m}/replies` (`ChannelMessage.Send`).
- **Minste delegerte sett for v1-scope (mail + chat, ikke kanaler)**: `Mail.ReadWrite`, `Mail.Send`, `Chat.Read`, `ChatMessage.Send`. Ingen av disse krever admin consent.

## 1. Mail: `message`

Kilde: [message resource type](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0)

### Felt tower trenger

| Felt | Type | Hvorfor tower trenger det |
| --- | --- | --- |
| `id` | String | Mål for `reply`/`replyAll`/`createReply`. Endres når meldingen flyttes mellom mapper, med mindre `Prefer: IdType="ImmutableId"` brukes. |
| `conversationId` | String | "The ID of the conversation the email belongs to." Grupperer meldinger til én Tråd. |
| `subject` | String | Vise Tråd. |
| `from` | recipient | Avsender. Avgjør også om siste melding er fra meg (= ingen svar trengs). |
| `toRecipients`, `ccRecipients` | recipient[] | Vise; triage (står jeg i To eller bare Cc?); avgjør reply vs replyAll. |
| `replyTo` | recipient[] | Graph-docs: svar skal gå til `replyTo` hvis satt, ikke `from`. |
| `receivedDateTime` | DateTimeOffset (ISO 8601, UTC) | Sortering i Tråd, alder for "haster". |
| `body` | itemBody | Innhold. `contentType` er `text` eller `html` ([itemBody](https://learn.microsoft.com/en-us/graph/api/resources/itembody?view=graph-rest-1.0)). |
| `bodyPreview` | String | "The first 255 characters of the message body", alltid tekst. Billig til liste og triage. |
| `isRead` | Boolean | Triage. Kan settes med `PATCH` ([update](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0)). |
| `importance` | `low`/`normal`/`high` | Triage-signal for "haster". |
| `hasAttachments` | Boolean | Vise at noe ikke kan leses (vedlegg er ute av v1). |
| `webLink` | String | "Åpne i Outlook" fra TUI-en. |

Nyttig, men valgfritt: `sentDateTime`, `conversationIndex` (posisjon i samtalen, binær), `flag` (followupFlag), `inferenceClassification` (`focused`/`other`, gratis triage-signal), `uniqueBody` (bare den nye delen av meldingen, uten sitert historikk; må hentes med `$select=uniqueBody`), `internetMessageId`, `isDraft`, `parentFolderId`.

`recipient` er `{"emailAddress": {"name": "...", "address": "..."}}` (se eksempler i [reply](https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0) og [createReply](https://learn.microsoft.com/en-us/graph/api/message-createreply?view=graph-rest-1.0)).

### Body-format

- List messages returnerer body som HTML som standard; header `Prefer: outlook.body-content-type="text"` gir tekst for `body` og `uniqueBody` ([list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0)).
- Konsekvens for mock: tillat begge `contentType`-verdier, men la `tower mock` generere `text` for enkelhet. Den ekte adapteren kan be om tekst via headeren.
- Merk at `body` i en mail inneholder sitert historikk. `uniqueBody` gir bare det nye. For agenten er `uniqueBody` per melding renere enn hele `body`. Mock kan nøye seg med `body` som bare det nye innholdet (det er i praksis det `uniqueBody` gir).

### Lese mail

`GET /me/messages`, `GET /me/mailFolders/{id}/messages`. Standard sidestørrelse 10, `$top` 1–1000, paging via `@odata.nextLink`. Bruk `$select` for ytelse. Ved `$filter` + `$orderby` må orderby-feltene også stå først i filteret, ellers `InefficientFilter` ([list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0)).

## 2. Teams: `chat` og `chatMessage`

Kilder: [chat](https://learn.microsoft.com/en-us/graph/api/resources/chat?view=graph-rest-1.0), [chatMessage](https://learn.microsoft.com/en-us/graph/api/resources/chatmessage?view=graph-rest-1.0)

### `chat`: felt tower trenger

| Felt | Hvorfor |
| --- | --- |
| `id` | Mål for `POST /chats/{chat-id}/messages`. Format f.eks. `19:...@thread.v2` (gruppe) eller `19:{userA}_{userB}@unq.gbl.spaces` (1:1). Skal behandles som opak. |
| `chatType` | `oneOnOne`, `group`, `meeting`, `unknownFutureValue`. |
| `topic` | Tittel; "Only available for group chats", ellers `null`. |
| `members` | Relasjon (`conversationMember`, i praksis `aadUserConversationMember` med `displayName`, `userId`, `email`). Hentes med `$expand=members` (maks 25 medlemmer i expand) ([list chats](https://learn.microsoft.com/en-us/graph/api/chat-list?view=graph-rest-1.0)). Trengs for å navngi 1:1-chatter som mangler `topic`. |
| `viewpoint.lastMessageReadDateTime` | Ulest-status. Docs: sammenlign `lastMessagePreview.createdDateTime` med `viewpoint.lastMessageReadDateTime` for å se om brukeren har lest alt ([list chats, eks. 4](https://learn.microsoft.com/en-us/graph/api/chat-list?view=graph-rest-1.0)). Bare fylt i delegert kontekst. |
| `lastMessagePreview` | Billig liste-visning (`$expand=lastMessagePreview`, bare på list chats). |
| `webUrl` | "Åpne i Teams". |

Teams har **ikke** `isRead` per melding. Ulest = `createdDateTime > viewpoint.lastMessageReadDateTime`.

### `chatMessage`: felt tower trenger

| Felt | Hvorfor |
| --- | --- |
| `id` | Unik innen chatten (ikke globalt). |
| `chatId` | Kobler meldingen til chatten. `null` for kanalmeldinger. |
| `messageType` | `message`, `chatEvent`, `typing`, `systemEventMessage`, `unknownFutureValue`. Tower må filtrere vekk alt som ikke er `message` (systemhendelser har `from: null` og `body.content = "<systemEventMessage/>"`) ([list messages in chat](https://learn.microsoft.com/en-us/graph/api/chat-list-messages?view=graph-rest-1.0)). |
| `createdDateTime` | Sortering, ulest-sjekk. |
| `from` | `chatMessageFromIdentitySet`: `{application, device, user}`; for personer er `user = {id, displayName, userIdentityType: "aadUser"}`. Bots har `application` i stedet. |
| `body` | itemBody. "The content is always in HTML if the chat message contains a chatMessageMention." I praksis er mye Teams-innhold HTML. |
| `importance` | `normal`, `high`, `urgent`. Triage. |
| `mentions` | Om jeg er @-nevnt: sterkt triage-signal. |
| `replyToId` | Bare for kanalmeldinger: id til rotmeldingen. Gjelder ikke chat. |
| `subject` | Valgfri, sjelden brukt i chat. |
| `webUrl` | Lenke (ofte `null` i chat-eksemplene). |

Nyttig, men valgfritt: `lastModifiedDateTime`, `lastEditedDateTime`, `deletedDateTime`, `attachments`, `reactions`, `channelIdentity` (`{teamId, channelId}` for kanalmeldinger).

### Lese chat

- `GET /me/chats` (eller `/chats`), `$expand=members` eller `lastMessagePreview`, `$top` maks 50, `$orderby=lastMessagePreview/createdDateTime desc` ([list chats](https://learn.microsoft.com/en-us/graph/api/chat-list?view=graph-rest-1.0)).
- `GET /chats/{chat-id}/messages`: `$top` maks 50; `$orderby` bare `lastModifiedDateTime` eller `createdDateTime` **synkende**; `$filter` bare på dato ([list messages in chat](https://learn.microsoft.com/en-us/graph/api/chat-list-messages?view=graph-rest-1.0)). Adapteren må reversere for kronologisk visning.

### Kanal-tråder (utenfor v1, men tatt med for sømmen)

En kanal-Tråd er en rotmelding + `replies`. Rotmeldinger: `GET /teams/{t}/channels/{c}/messages`. Svar: `GET .../messages/{m}/replies` (`$top` maks 50), krever `ChannelMessage.Read.All` som **krever admin consent** ([list replies](https://learn.microsoft.com/en-us/graph/api/chatmessage-list-replies?view=graph-rest-1.0), [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)).

## 3. Kall for å svare

| Handling | Kall | Body | Respons | Minste delegerte tillatelse |
| --- | --- | --- | --- | --- |
| Svar til avsender | `POST /me/messages/{id}/reply` | `{"comment": "..."}` **eller** `{"message": {"body": {...}}}`, ikke begge (400) | `202 Accepted`, tom body | `Mail.Send` |
| Svar til alle | `POST /me/messages/{id}/replyAll` | `{"comment": "..."}` | `202 Accepted` | `Mail.Send` |
| Lag svarutkast | `POST /me/messages/{id}/createReply` (også `createReplyAll`) | ingen påkrevd | `201 Created` + utkast-`message` | `Mail.ReadWrite` |
| Rediger utkast | `PATCH /me/messages/{draftId}` | `body`, `toRecipients` osv.; bare når `isDraft = true` | `200 OK` | `Mail.ReadWrite` |
| Send utkast | `POST /me/messages/{draftId}/send` | ingen | `202 Accepted` | `Mail.Send` |
| Marker lest | `PATCH /me/messages/{id}` med `{"isRead": true}` | | `200 OK` | `Mail.ReadWrite` |
| Svar i chat | `POST /chats/{chat-id}/messages` | `{"body": {"contentType": "text"/"html", "content": "..."}}` | `201 Created` + `chatMessage` | `ChatMessage.Send` (høyere: `Chat.ReadWrite`) |
| Svar i kanal-tråd | `POST /teams/{t}/channels/{c}/messages/{m}/replies` | samme som chat; bare `body` er påkrevd | `201 Created` | `ChannelMessage.Send` |

Kilder: [reply](https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0), [replyAll](https://learn.microsoft.com/en-us/graph/api/message-replyall?view=graph-rest-1.0), [createReply](https://learn.microsoft.com/en-us/graph/api/message-createreply?view=graph-rest-1.0), [update](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0), [send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0), [chat post messages](https://learn.microsoft.com/en-us/graph/api/chat-post-messages?view=graph-rest-1.0), [channel replies](https://learn.microsoft.com/en-us/graph/api/chatmessage-post-replies?view=graph-rest-1.0).

Detaljer som påvirker sømmen:

- `reply`/`replyAll`/`send` lagrer i Sendte elementer og returnerer **ingen** id. Tower kan ikke hente den sendte meldingen fra svaret; den dukker opp i neste listing med samme `conversationId`.
- `reply` `comment` legges over den siterte originalen (Outlook-stil). Med `message.body` styrer du hele innholdet selv.
- Chat-POST kan ikke lage nye chatter; `chat-id` må komme fra list chats.
- Ingen av mail-kallene finnes for kanal; ingen av chat-kallene har "utkast". Teams har ikke noe server-side utkast, så Utkast-begrepet i tower er alltid lokalt for Teams.
- Personlige Microsoft-kontoer støtter ikke chat-API-ene (bare jobb/skole).

## 4. Tillatelser (delegert)

Fra [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference) og API-sidene over:

| Tillatelse | Gir | Admin consent | Trengs til |
| --- | --- | --- | --- |
| `Mail.ReadBasic` | Lese mail unntatt bl.a. body og vedlegg | Nei | Ikke nok: tower trenger body. |
| `Mail.Read` | Lese mail | Nei | Lese tråder. |
| `Mail.ReadWrite` | Lese/skrive/slette mail, **ikke sende** | Nei | `isRead`, `createReply`, `PATCH`-utkast. Dekker også lesing. |
| `Mail.Send` | Sende mail som brukeren | Nei | `reply`, `replyAll`, `send`. |
| `Chat.ReadBasic` | Navn og medlemmer i chatter, ikke meldinger | Nei | Ikke nok. |
| `Chat.Read` | Lese 1:1- og gruppechatter | Nei | List chats + list messages. |
| `ChatMessage.Send` | Sende chatmeldinger | Nei | Svar i chat. |
| `ChannelMessage.Read.All` | Lese kanalmeldinger | **Ja** | Kanal-tråder (utenfor v1). |
| `ChannelMessage.Send` | Sende kanalmeldinger | Nei | Svar i kanal (utenfor v1). |

Minste sett for mail + chat: **`Mail.ReadWrite` + `Mail.Send` + `Chat.Read` + `ChatMessage.Send`**. Dropper man markering som lest og server-side utkast holder `Mail.Read` + `Mail.Send`.

## 5. Anbefalt mock-format

Prinsipp: hver fil er én Tråd. Innholdet er **ordrett Graph-objekter** (samme feltnavn, samme nesting, ISO 8601 UTC), pakket i en tynn konvolutt som speiler Graph-listesvar (`value`). Bare felt fra lista over tas med; alt annet kan utelates fordi Graph-klienter uansett må tåle manglende felt. Da kan den ekte adapteren senere bare fylle konvolutten fra `GET`-kall uten å skrive om parseren.

Konvolutt-felt med prefiks `_tower` er tower-egne og finnes ikke i Graph. Hold dem til et minimum.

### `mail/<conversationId>.json`

```json
{
  "_towerChannel": "mail",
  "conversationId": "AAQkADMock-conv-0001",
  "value": [
    {
      "id": "AAMkADMock-msg-0001",
      "conversationId": "AAQkADMock-conv-0001",
      "subject": "Leveranse til fredag?",
      "from": { "emailAddress": { "name": "Kari Nordmann", "address": "kari@kunde.no" } },
      "toRecipients": [ { "emailAddress": { "name": "Sander Hurlen", "address": "sander@visense.no" } } ],
      "ccRecipients": [ { "emailAddress": { "name": "Ola Prosjekt", "address": "ola@kunde.no" } } ],
      "replyTo": [],
      "receivedDateTime": "2026-10-06T08:12:00Z",
      "sentDateTime": "2026-10-06T08:11:58Z",
      "body": { "contentType": "text", "content": "Hei Sander,\nRekker dere leveransen til fredag, eller bør vi flytte demoen?\nKari" },
      "bodyPreview": "Hei Sander, Rekker dere leveransen til fredag, eller bør vi flytte demoen? Kari",
      "isRead": false,
      "importance": "high",
      "hasAttachments": false,
      "webLink": "https://outlook.office365.com/owa/?ItemID=mock-0001"
    },
    {
      "id": "AAMkADMock-msg-0002",
      "conversationId": "AAQkADMock-conv-0001",
      "subject": "RE: Leveranse til fredag?",
      "from": { "emailAddress": { "name": "Ola Prosjekt", "address": "ola@kunde.no" } },
      "toRecipients": [ { "emailAddress": { "name": "Kari Nordmann", "address": "kari@kunde.no" } } ],
      "ccRecipients": [ { "emailAddress": { "name": "Sander Hurlen", "address": "sander@visense.no" } } ],
      "replyTo": [],
      "receivedDateTime": "2026-10-06T09:40:00Z",
      "sentDateTime": "2026-10-06T09:39:57Z",
      "body": { "contentType": "text", "content": "Demoen kan i verste fall flyttes til mandag." },
      "bodyPreview": "Demoen kan i verste fall flyttes til mandag.",
      "isRead": false,
      "importance": "normal",
      "hasAttachments": false,
      "webLink": "https://outlook.office365.com/owa/?ItemID=mock-0002"
    }
  ]
}
```

Meldinger i `value` sorteres stigende på `receivedDateTime` i fila (Graph gir hva enn `$orderby` sier; adapteren normaliserer).

### `teams/<chat-id>.json`

```json
{
  "_towerChannel": "teams",
  "chat": {
    "id": "19:mock-0001@thread.v2",
    "chatType": "group",
    "topic": "Prosjekt Kunde X",
    "webUrl": "https://teams.microsoft.com/l/chat/19%3Amock-0001%40thread.v2/0",
    "viewpoint": { "isHidden": false, "lastMessageReadDateTime": "2026-10-06T10:00:00Z" },
    "members": [
      { "@odata.type": "#microsoft.graph.aadUserConversationMember", "userId": "u-sander", "displayName": "Sander Hurlen", "email": "sander@visense.no" },
      { "@odata.type": "#microsoft.graph.aadUserConversationMember", "userId": "u-kari", "displayName": "Kari Nordmann", "email": "kari@kunde.no" }
    ]
  },
  "value": [
    {
      "id": "1759744800000",
      "chatId": "19:mock-0001@thread.v2",
      "messageType": "message",
      "createdDateTime": "2026-10-06T10:00:00Z",
      "from": { "application": null, "device": null, "user": { "id": "u-sander", "displayName": "Sander Hurlen", "userIdentityType": "aadUser" } },
      "body": { "contentType": "text", "content": "Jeg sjekker status med teamet." },
      "importance": "normal",
      "mentions": []
    },
    {
      "id": "1759748400000",
      "chatId": "19:mock-0001@thread.v2",
      "messageType": "message",
      "createdDateTime": "2026-10-06T11:00:00Z",
      "from": { "application": null, "device": null, "user": { "id": "u-kari", "displayName": "Kari Nordmann", "userIdentityType": "aadUser" } },
      "body": { "contentType": "html", "content": "<p><at id=\"0\">Sander</at> har du noe nytt?</p>" },
      "importance": "high",
      "mentions": [
        { "id": 0, "mentionText": "Sander", "mentioned": { "user": { "id": "u-sander", "displayName": "Sander Hurlen", "userIdentityType": "aadUser" } } }
      ]
    }
  ]
}
```

Ulest i denne Tråden: meldingen 11:00 er nyere enn `viewpoint.lastMessageReadDateTime` (10:00). Chat-id-er i Graph er tidsstempel-lignende strenger (eks. `"1616964509832"`); mock gjør det samme.

`mentions`-formen (`id`, `mentionText`, `mentioned.user`) er fra [chatMessageMention](https://learn.microsoft.com/en-us/graph/api/resources/chatmessagemention?view=graph-rest-1.0); ikke verifisert linje for linje i denne runden, men feltnavnene matcher Graph-eksemplene.

### `outbox/<timestamp>-<tråd>.json`

Speil **request-bodyen** til kallet den ekte adapteren ville gjort, pluss hvilket kall:

```json
{ "_towerChannel": "mail", "method": "POST", "path": "/me/messages/AAMkADMock-msg-0002/replyAll",
  "body": { "comment": "Hei Kari, vi rekker fredag. Sander" } }
```

```json
{ "_towerChannel": "teams", "method": "POST", "path": "/chats/19:mock-0001@thread.v2/messages",
  "body": { "body": { "contentType": "text", "content": "Ja, vi er i rute til fredag." } } }
```

Da blir bytte til ekte Graph i praksis "send denne requesten i stedet for å skrive fila".

### "Meg"-identitet

Både triage ("siste melding er fra meg, ingen svar trengs") og reply vs replyAll krever å vite hvem jeg er: e-postadresse for mail (`from.emailAddress.address`), AAD-bruker-id for Teams (`from.user.id`). I Graph kommer dette fra `GET /me`. I mock: én konfig-verdi (f.eks. `me.json` i data-roten med `{"mail": "...", "id": "u-sander"}`), ikke per Tråd.

## Åpne punkter

- Mail-`body` med sitert historikk vs `uniqueBody`: ekte adapter bør trolig hente `uniqueBody` for agenten. Mock antar `body` = bare nytt innhold.
- HTML-body (særlig Teams) må strippes til tekst før visning og agent. Gjelder ekte data; mock kan bruke `text` stort sett, men bør ha minst ett HTML-eksempel med mention for å teste stripping.
- Kanal-tråder trenger admin consent for lesing; derfor naturlig å holde dem utenfor v1 også i ekte modus.
