# Tower

Terminal-cockpit som forbereder svar på innkommende jobbkommunikasjon, slik at jeg bare vurderer og sender.

## Language

**Kanal**:
En kilde for innkommende kommunikasjon, f.eks. mail eller Teams.
_Avoid_: Kilde, integrasjon, provider

**Tråd**:
Én samtale i en kanal som kan trenge svar; enheten tower forbereder svar på. Nye meldinger i tråden gjør det gamle utkastet utdatert.
_Avoid_: Henvendelse, melding, sak

**Melding**:
Én enkelt ytring fra én person i en Tråd.
_Avoid_: Post, innlegg, mail

**Utkast**:
Et svar på en tråd, foreslått av en bakgrunnsagent, som venter på min vurdering før det eventuelt sendes.
_Avoid_: Forslag, draft, svarforslag

**Kunnskapsbase**:
Varige fakta om jobben og meg, bygget fra svar jeg har sendt og research gjort for å svare.
_Avoid_: Minne, memory, KB

**Research**:
Fakta Utkast-agenten finner selv i kilder utenfor Tråden og Kunnskapsbasen når jeg ber om det, alltid med kilde. Går videre til Kuratoren.
_Avoid_: Oppslag, søk, funn

**Kurator**:
Bakgrunnsagenten som oppdaterer Kunnskapsbasen etter hvert svar jeg sender, med fakta fra Tråden og stil fra hvordan jeg endret Utkastet.
_Avoid_: Minneagent, KB-agent

**Triage**:
Klassifisering av en Tråd (trenger svar, bare info, haster) som avgjør om det lages et Utkast. Gjøres på nytt ved hver ny melding.
_Avoid_: Sortering, prioritering, kategori

**Utsett**:
Å skjule en Tråd til et valgt tidspunkt, eller til en ny melding kommer inn hvis det skjer først.
_Avoid_: Snooze, parkere, senere
