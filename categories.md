---
layout: page
title: 카테고리
permalink: /categories/
---

<ul>
  {% for category in site.categories %}
    <li>
      <h2>{{ category[0] }}</h2>
      <ul>
        {% for post in category[1] %}
          <li>
            <a href="{{ post.url | relative_url }}">{{ post.title }}</a> ({{ post.date | date: "%Y-%m-%d" }})
          </li>
        {% endfor %}
      </ul>
    </li>
  {% endfor %}
endloop