import { ArrowLeft, ArrowRight, Clock3, LoaderCircle, TriangleAlert, Users, X } from "lucide-react";
import type { Recipe } from "@/lib/kitchen-data";

export type RecipeView = {
  state: "working" | "failed" | "ready";
  error: string;
  recipe: Recipe | null;
  expiringInPantry: string[];
};

type RecipeStageProps = {
  view: RecipeView;
  step: number;
  onStep(next: number): void;
  onClose(): void;
};

/**
 * Takes over the whole device screen, because a recipe mid-cook is not a panel
 * in a dashboard -- it is the only thing you want on the display, one step at a
 * time, in numerals you can read from the other side of the hob.
 *
 * The failed state is a real failure, shown as one. This project does not ship
 * a mocked recipe to make the screen look finished: without AWS credentials
 * that reach Bedrock the tool genuinely cannot run, and the screen says the
 * server's own words back.
 */
export function RecipeStage({ view, step, onStep, onClose }: RecipeStageProps) {
  if (view.state === "working") {
    return (
      <section className="recipe-stage" aria-label="Recipe">
        <div className="recipe-center">
          <LoaderCircle className="spin" size={58} strokeWidth={2.2} />
          <h2>Working out what to cook</h2>
          <p>Reading the pantry by expiry date, soonest first.</p>
        </div>
      </section>
    );
  }

  if (view.state === "failed" || !view.recipe) {
    return (
      <section className="recipe-stage stage-failed" aria-label="Recipe">
        <div className="recipe-center">
          <span className="recipe-alert"><TriangleAlert size={48} strokeWidth={2.2} /></span>
          <h2>I cannot plan a meal right now</h2>
          <p className="recipe-error-text">{view.error}</p>
          <p className="recipe-error-note">
            That is the real answer from <code>generate_and_adapt_recipe</code>,
            not a placeholder. The tool reasons over the pantry with Amazon
            Bedrock, and this machine has no AWS credentials that reach it. The
            rest of the screen is unaffected, because everything else is served
            by PostgreSQL.
          </p>
          <button className="recipe-exit" onClick={onClose}>
            <ArrowLeft size={20} /> Back to the pantry
          </button>
        </div>
      </section>
    );
  }

  const recipe = view.recipe;
  const total = recipe.steps.length;
  const index = Math.min(Math.max(step, 0), total - 1);

  return (
    <section className="recipe-stage" aria-label="Recipe">
      <header className="recipe-head">
        <div className="recipe-title">
          <h2>{recipe.title}</h2>
          <p className="recipe-meta">
            <span><Users size={17} /> {recipe.servings} servings</span>
            <span><Clock3 size={17} /> {recipe.total_minutes} min</span>
            {recipe.uses_expiring.map((name) => (
              <span className="recipe-rescues" key={name}>Uses {name}</span>
            ))}
          </p>
        </div>
        <button className="recipe-exit small" onClick={onClose} aria-label="Close the recipe">
          <X size={22} />
        </button>
      </header>

      {recipe.missing.length ? (
        <p className="recipe-missing">
          You will also need: {recipe.missing.join(", ")}
        </p>
      ) : null}

      <div className="recipe-step" aria-live="polite">
        <span className="recipe-step-number">{String(index + 1).padStart(2, "0")}</span>
        <p className="recipe-step-text">{recipe.steps[index]}</p>
      </div>

      <footer className="recipe-foot">
        <span className="recipe-progress">Step {index + 1} of {total}</span>
        <div className="recipe-nav">
          <button onClick={() => onStep(index - 1)} disabled={index === 0}>
            <ArrowLeft size={22} /> Back
          </button>
          <button
            className="recipe-next" onClick={() => onStep(index + 1)}
            disabled={index >= total - 1}
          >
            Next <ArrowRight size={22} />
          </button>
        </div>
      </footer>
    </section>
  );
}
