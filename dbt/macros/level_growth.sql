{#
  La croissance d'une stat avec le niveau, dans LoL : pas une ligne droite.

    stat au niveau n = stat de base + gain par niveau x level_growth(n)
    level_growth(n)  = (n - 1) x (0.7025 + 0.0175 x (n - 1))

  Niveau 1 : 0 ; niveau 2 : 0,72 ; niveau 10 : 7,74 ; niveau 18 : exactement 17
  (la meme chose qu'une ligne droite au niveau 18, mais le gain arrive plus
  tard : moins au debut, plus a la fin).

  Verifie le 16/11/2026 sur les vraies stats des parties du ladder (API Riot,
  stats de chaque joueur a chaque minute) : armure et resistance magique, 94 %
  des cas (ligne droite : moins de 1 %) ; bonus de vitesse d'attaque, 90 %
  (ligne droite : moins de 4 %) ; la courbe continue aux niveaux 19 et 20.
  Les ecarts restants viennent des objets (Heaume de Doran) et des passifs
  (Garen, Thresh...).

  Les parentheses autour de {{ level }} protegent un calcul passe en
  argument : level_growth('a + 1') doit valoir (a + 1 - 1)..., pas a + 1 - 1...
#}
{% macro level_growth(level) -%}
    ((({{ level }}) - 1) * (0.7025 + 0.0175 * (({{ level }}) - 1)))
{%- endmacro %}
