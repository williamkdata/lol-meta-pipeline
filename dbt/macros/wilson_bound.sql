{#
    Une borne de l'intervalle de Wilson a 95 % pour un taux de victoire :
    la fourchette ou se trouve probablement le VRAI taux, compte tenu du
    nombre de parties. 3 victoires sur 4 -> [0,301 ; 0,954] ; 220 sur 400
    -> [0,501 ; 0,598].

    sens = '-' pour la borne basse, '+' pour la borne haute.
    z = 1.96 pour 95 %.

    Formule : (p + z^2/2n  +/-  z * racine(p(1-p)/n + z^2/4n^2)) / (1 + z^2/n)
    En BigQuery, / renvoie toujours un decimal : wins / games ne tronque pas.
#}
{% macro wilson_bound(wins, games, sens, z=1.96) %}
(
    (
        {{ wins }} / {{ games }}
        + {{ z }} * {{ z }} / (2 * {{ games }})
        {{ sens }} {{ z }} * SQRT(
            {{ wins }} / {{ games }} * (1 - {{ wins }} / {{ games }}) / {{ games }}
            + {{ z }} * {{ z }} / (4 * {{ games }} * {{ games }})
        )
    )
    / (1 + {{ z }} * {{ z }} / {{ games }})
)
{% endmacro %}
