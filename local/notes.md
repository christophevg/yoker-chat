# Notes

## TODO

- investigate issue with reading PERSONAL and not doing anything with it
  - who produces what logs? yoker/yoker-chat/roomz
    - improve logging
      - remove stupid redacted

- fix name setting
- fix name/bot mention trigger

✓ Listening for messages... (Press Ctrl+C to exit)
2026-05-20T18:37:45.292215Z [info     ] message_received               bot_email=contact@christophe.vg bot_name=Eira content=[REDACTED] sender_email=contact@christophe.vg sender_name=None
2026-05-20T18:37:45.294300Z [info     ] message_mentioned              content_preview=[REDACTED] sender=[REDACTED]
2026-05-20T18:37:45.294731Z [info     ] message_queued                 message_preview=[REDACTED] queue_size=1
2026-05-20T18:37:45.295294Z [info     ] processing_message             message_preview=[REDACTED]
2026-05-20T18:37:45.297152Z [info     ] turn_started                   message_preview=[REDACTED]
2026-05-20T18:38:00.524796Z [info     ] response_complete              length=110
2026-05-20T18:38:00.528224Z [info     ] guardrail_allowed              path=/Users/xtof/Workspace/agentic/yoker-chat/PERSONAL.md tool=read
2026-05-20T18:38:00.528403Z [info     ] guardrail_allowed              path=PERSONAL.md tool=read
2026-05-20T18:38:00.528684Z [info     ] guardrail_allowed              path=/Users/xtof/Workspace/agentic/yoker-chat/PERSONAL.md tool=read
2026-05-20T18:38:00.529161Z [info     ] read_success                   bytes=5727 path=/Users/xtof/Workspace/agentic/yoker-chat/PERSONAL.md
2026-05-20T18:38:13.779397Z [info     ] response_complete              length=1146
2026-05-20T18:38:13.780868Z [info     ] turn_completed                 response_length=1036 tool_calls_count=0
2026-05-20T18:38:13.836054Z [info     ] message_received               bot_email=contact@christophe.vg bot_name=Eira content=[REDACTED] sender_email=contact@christophe.vg sender_name=None
2026-05-20T18:38:13.836300Z [info     ] filtered_unmentioned_message   content_preview=[REDACTED] sender=[REDACTED]
2026-05-20T18:38:13.836568Z [info     ] response_sent                  length=110 preview=[REDACTED]
