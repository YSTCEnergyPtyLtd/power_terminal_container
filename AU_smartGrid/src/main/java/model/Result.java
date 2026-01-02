package main.java.model;

import java.util.ArrayList;

public class Result {
    private double benefit;
    private int cost = 0;
    private int iteration = 0;
    private double timeConsumption = 0;
    private double revenue = 0;
    private ArrayList<Decision> decisions = new ArrayList<>();

    public double getBenefit() {
        return benefit;
    }
    public void setBenefit(double benefit) {
        this.benefit = benefit;
    }
    public int getCost() {
        return cost;
    }
    public void setCost(int cost) {
        this.cost = cost;
    }
    public int getIteration() {
        return iteration;
    }
    public void setIteration(int iteration) {
        this.iteration = iteration;
    }
    public double getTimeConsumption() {
        return timeConsumption;
    }
    public void setTimeConsumption(double timeConsumption) {
        this.timeConsumption = timeConsumption;
    }
    public double getRevenue() {
        return revenue;
    }
    public void setRevenue(double revenue) {
        this.revenue = revenue;
    }
    public ArrayList<Decision> getDecisions() {
        return decisions;
    }
    public void setDecisions(ArrayList<Decision> decisions) {
        this.decisions = decisions;
    }


    public Result() {

    }

    public Result(Result result) {
        this.benefit = result.benefit;
        this.cost = result.cost;
        this.iteration = result.iteration;
        this.timeConsumption = result.timeConsumption;
        this.revenue = result.revenue;
        for(int i=0;i<result.decisions.size();i++) {
            this.decisions.add(new Decision(result.decisions.get(i)));
        }

    }

    public static double getOverallRevenue(Result result, Station station) {
        double revenue = 0;

        for(int i=0;i<result.getDecisions().size();i++) {
            for(int j=0;j<ConstNum.timeSlots;j++) {
                if(result.getDecisions().get(i).getDc()[j]!=0) {
                    revenue += station.getPrice().get(j) * (result.getDecisions().get(i).getDc()[j]*result.getDecisions().get(i).getSpeed()[j]*ConstNum.longPerTime)*(1-result.getDecisions().get(i).getCost()[j]);
                }
            }
        }

        return revenue;
    }



}
