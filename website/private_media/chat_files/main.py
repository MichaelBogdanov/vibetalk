"""
Исправленная версия:
- модель: F = k * x (удлинение x в мм, сила F в Н)
- аналитический МНК для наклона через ноль:
- стандартная ошибка наклона из регрессии
- оценка влияния погрешности dx на k через Monte-Carlo
- корректный вывод и построение графиков с горизонтальными погрешностями
"""
import numpy as np
import matplotlib.pyplot as plt

all_x = ((22, 41, 50, 63),
         (13, 15, 20, 24),
         (39, 57, 72, 85),
         ( 8, 13, 17, 23))
all_y = (0.490, 0.686, 0.882, 1.078)
dx = 2.0  # абсолютная погрешность по x (мм)
mc_samples = 5000  # количество итераций Monte-Carlo для оценки влияния dx

def fit_slope_through_origin(x, y):
    """
    МНК через начало координат (модель y = k * x):
    k = sum(x*y) / sum(x^2)
    Возвращает k и стандартную ошибку оценки k (предполагая погрешности в y).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    denom = np.sum(x * x)
    if denom == 0:
        raise ValueError("Сумма квадратов x равна нулю — деление на ноль.")
    k = np.sum(x * y) / denom

    # Остатки и оценка дисперсии ошибки (если считать шум в y)
    residuals = y - k * x
    n = len(x)
    if n > 1:
        # несмещённая оценка дисперсии остатков
        sigma2 = np.sum(residuals**2) / (n - 1)
        # стандартная ошибка k (формула для модели через начало координат)
        # Var(k) = sigma2 / sum(x^2)
        se_k = np.sqrt(sigma2 / denom)
    else:
        se_k = np.nan

    return k, se_k, residuals

def mc_uncertainty_due_to_x(x, y, dx, samples=2000, random_seed=0):
    """
    Monte-Carlo: генерируем смещения x' ~ N(x, dx) и считаем распределение k.
    Возвращаем среднее и std для распределения k.
    """
    rng = np.random.default_rng(random_seed)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ks = np.empty(samples)
    for i in range(samples):
        x_pert = x + rng.normal(0.0, dx, size=x.shape)
        denom = np.sum(x_pert * x_pert)
        if denom == 0:
            ks[i] = np.nan
        else:
            ks[i] = np.sum(x_pert * y) / denom
    ks = ks[~np.isnan(ks)]
    return np.mean(ks), np.std(ks), ks

# Итерация по каждому набору измерений
for i, x_set in enumerate(all_x):
    x = np.array(x_set, dtype=float)
    y = np.array(all_y, dtype=float)  # y одинаковы для всех наборов — похоже, это так по данным

    # Нарисуем точки с горизонтальными погрешностями
    plt.errorbar(x, y, xerr=dx, fmt='o', label='Измерения (x ± dx)', capsize=4)

    # Аналитическая подгонка
    k, se_k, residuals = fit_slope_through_origin(x, y)

    # Оценка влияния dx через Monte-Carlo
    mc_mean_k, mc_std_k, ks = mc_uncertainty_due_to_x(x, y, dx, samples=mc_samples, random_seed=42)

    # Подбор диапазона для линии
    x_plot = np.linspace(0, x.max() * 1.1, 300)
    y_plot = k * x_plot

    plt.plot(x_plot, y_plot, color='red', label=f'МНК: y = k·x\nk = {k:.4f} ± {se_k:.4f} (SE_y)\nMC по dx: σ_k ≈ {mc_std_k:.4f}')

    plt.xlabel('Удлинение, мм')
    plt.ylabel('Сила упругости, Н')
    plt.title(f'График №{i + 1}')
    plt.grid(True)
    plt.legend(loc='best')

    # Печатаем численные результаты
    print(f'Набор #{i+1}')
    print(f'  x: {x}')
    print(f'  y: {y}')
    print(f'  Найденный k = {k:.6f} Н/мм')
    print(f'  Стандартная ошибка наклона (предполагая шум в y): SE(k) = {se_k:.6f}')
    print(f'  Monte-Carlo (смещение x ~ N(0, {dx})) -> mean(k)={mc_mean_k:.6f}, std(k)={mc_std_k:.6f}')
    print(f'  Остатки (y - k*x): {residuals}\n')

    plt.show()

input("Нажмите Enter для выхода...")
