/**
 * Открыть выдачу уже ЗАПУЩЕННОГО интента.
 *
 * Мастер и страницы активного интента не должны оставаться под выдачей: системный back тогда
 * возвращает человека в уже завершённое создание. Сначала сворачиваем любую глубину до главной,
 * затем кладём выдачу одним экраном поверх неё. Получается стабильный стек [home, results].
 */
type ResultsRouter = {
  dismissTo: (href: '/home') => void;
  navigate: (href: '/results') => void;
};

export function openResults(router: ResultsRouter) {
  router.dismissTo('/home');
  router.navigate('/results');
}
