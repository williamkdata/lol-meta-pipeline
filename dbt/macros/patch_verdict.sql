{#
    Le verdict d'une experience de patch : le taux observe a-t-il bouge dans
    le sens predit par le moteur theorique ? On compare l'ancien patch au
    nouveau avec leurs fourchettes de Wilson :
      - confirme       : bon sens, fourchettes separees (prouve) ;
      - meme_sens      : bon sens, fourchettes qui se chevauchent ;
      - sens_contraire : sens oppose, fourchettes qui se chevauchent ;
      - contredit      : sens oppose, fourchettes separees (prouve) ;
      - stable         : exactement le meme taux ;
      - sans_donnees   : un des deux taux n'existe pas (0 joueur concerne).
    direction = 'hausse' ou 'baisse' (mart_patch_predictions).
#}
{% macro patch_verdict(direction, old_rate, old_low, old_high, new_rate, new_low, new_high) %}
CASE
    WHEN {{ old_rate }} IS NULL OR {{ new_rate }} IS NULL THEN 'sans_donnees'
    WHEN {{ new_rate }} = {{ old_rate }} THEN 'stable'
    WHEN ({{ direction }} = 'hausse') = ({{ new_rate }} > {{ old_rate }}) THEN
        IF({{ new_low }} > {{ old_high }} OR {{ new_high }} < {{ old_low }}, 'confirme', 'meme_sens')
    ELSE
        IF({{ new_low }} > {{ old_high }} OR {{ new_high }} < {{ old_low }}, 'contredit', 'sens_contraire')
END
{% endmacro %}
