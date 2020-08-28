
SELECT res.date, res.result,
COUNT(*) AS "count",
SUM("duration") AS "AllDuration",
pr.name as "project", 
srv.name as "server" 
	FROM public."RecognitionResult" res
	JOIN public."Project" pr ON pr.id = project_id
	JOIN public."Server" srv ON srv.id = server_id
		WHERE res."date" = '28/08/2020' 
			GROUP BY res."result", res."date", pr.name, srv.name