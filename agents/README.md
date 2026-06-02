# TechTracker agents

Агенты вынесены в отдельный проект:

```text
/home/zulixo/projects/tracker-agent
```

Рекомендуемый внешний GitHub-репозиторий: `tracker-agent` или `TechTrackerAgent`.

В основном проекте TechTracker должны оставаться только:

- backend/API для токенов агентов;
- UI вкладка `Настройки -> Инсталяторы`;
- логика чтения последнего GitHub Release внешнего репозитория агента;
- проверка наличия asset `TechTrackerAgentInstaller.exe`.

Готовые установщики агента не нужно хранить в git основного проекта. Их следует публиковать как assets в GitHub Releases репозитория агента.

Если репозиторий агента приватный, на сервере TechTracker нужно задать `AGENT_RELEASE_GITHUB_TOKEN` или `GITHUB_TOKEN`, иначе GitHub API вернет `404` для `/releases/latest`.
