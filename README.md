Все переменные для подключения находятся в .env файлах, распологающихся на конечных серверах
Используется GithubActions (.github/Workflows) для пересборки кода на удаленном сервере при коммитах в ветвь master
Есть еще ветвь development, которая выступает в роли тестовой - для нее используется отдельный пайплайн 

